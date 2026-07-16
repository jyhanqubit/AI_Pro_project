"""GDELT GKG bulk-file provider (§7, §7.4). Pure logic — no network.

Covers slice-stamp enumeration, GKG row parsing, the NYC + theme filter, and the payload mapping
(real provenance + labelled GDELT tags, empty title — never a fabricated headline).
"""

from __future__ import annotations

import pytest

from pipelines.collectors.backfill import ProviderUnavailable
from pipelines.collectors.gdelt_bulk_provider import (
    GdeltBulkNewsProvider,
    gkg_file_url,
    gkg_row_to_payload,
    iter_slice_stamps,
    parse_gkg_row,
    row_matches,
)

# A minimal GKG 2.1 row: cols 0..9 with date, source, url, themes, locations (NYC).
_NYC_ROW = "\t".join(
    [
        "REC1",  # 0 GKGRECORDID
        "20260115131500",  # 1 V2.1DATE
        "1",  # 2
        "nytimes.com",  # 3 source
        "https://www.nytimes.com/2026/01/15/nyc-subway.html",  # 4 url
        "",  # 5
        "",  # 6
        "TAX_DISEASE;TRANSPORT;PROTEST",  # 7 V1Themes
        "",  # 8
        "3#New York, New York, United States#US#USNY#40.71#-74.0#12345",  # 9 V1Locations
    ]
)


def test_gkg_file_url() -> None:
    assert gkg_file_url("20260115131500").endswith("/20260115131500.gkg.csv.zip")


def test_iter_slice_stamps_quarter_hours() -> None:
    stamps = iter_slice_stamps("20260115130700", "20260115140000")
    # snaps 13:07 down to 13:00, then :15/:30/:45 up to (exclusive) 14:00
    assert stamps == [
        "20260115130000",
        "20260115131500",
        "20260115133000",
        "20260115134500",
    ]


def test_parse_gkg_row_extracts_fields() -> None:
    row = parse_gkg_row(_NYC_ROW)
    assert row is not None
    assert row["url"].endswith("nyc-subway.html")
    assert row["source"] == "nytimes.com"
    assert "TRANSPORT" in row["themes"]
    assert row["locations"][0][2] == "USNY"


def test_parse_gkg_row_rejects_short_rows() -> None:
    assert parse_gkg_row("only\tthree\tcols") is None


def test_row_matches_nyc_and_theme() -> None:
    row = parse_gkg_row(_NYC_ROW)
    assert row is not None
    assert row_matches(row, ("TRANSPORT",), require_nyc=True)
    # NYC but no matching theme -> drop
    assert not row_matches(row, ("MARITIME",), require_nyc=True)


def test_row_matches_rejects_non_nyc_when_required() -> None:
    non_nyc = _NYC_ROW.replace(
        "3#New York, New York, United States#US#USNY#40.71#-74.0#12345",
        "3#Chicago, Illinois, United States#US#USIL#41.8#-87.6#99",
    )
    row = parse_gkg_row(non_nyc)
    assert row is not None
    assert not row_matches(row, ("TRANSPORT",), require_nyc=True)
    assert row_matches(row, ("TRANSPORT",), require_nyc=False)  # theme-only filter


def test_payload_has_real_provenance_and_empty_title() -> None:
    row = parse_gkg_row(_NYC_ROW)
    assert row is not None
    p = gkg_row_to_payload(row)
    assert p["title"] == ""  # GKG has no headline; never fabricated
    assert p["text"].startswith("[GDELT GKG]")  # real labelled tags, not article prose
    assert "TRANSPORT" in p["text"]
    assert p["source"] == "nytimes.com"
    assert p["published_at"] == "2026-01-15T13:15:00+00:00"
    assert len(p["url_hash"]) == 64


def test_disabled_provider_degrades() -> None:
    with pytest.raises(ProviderUnavailable):
        GdeltBulkNewsProvider(enabled=False, start="20260115130000", end="20260115140000").fetch()


def test_missing_window_degrades() -> None:
    with pytest.raises(ProviderUnavailable, match="window"):
        GdeltBulkNewsProvider(enabled=True).fetch()


def test_fetch_dedups_across_slices(monkeypatch) -> None:
    p = GdeltBulkNewsProvider(
        enabled=True, start="20260115130000", end="20260115133000", theme_terms=("TRANSPORT",)
    )
    row = parse_gkg_row(_NYC_ROW)
    # same article URL returned in two adjacent slices -> one payload
    monkeypatch.setattr(p, "_fetch_slice", lambda stamp: [row])
    out = p.fetch()
    assert len(out) == 1
    assert out[0]["url"].endswith("nyc-subway.html")
