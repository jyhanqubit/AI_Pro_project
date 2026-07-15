"""Bulk-download Citi Bike trip history from the public S3 bucket (V2). CLAUDE.md §7.1.

One command fetches whole months of real Citi Bike trip data into ``data/raw/citibike/`` instead of
downloading each zip by hand. The bucket is listed to discover the actual filename for a month
(the naming has shifted over the years: ``YYYYMM-citibike-tripdata.zip``, older
``YYYYMM-citibike-tripdata.csv.zip``, and the Jersey City ``JC-…`` variants), so a month is matched
by content, not a guessed URL. Existing files are skipped (idempotent); optional extraction unzips
the CSVs next to the archive.

Needs outbound network (the ``s3.amazonaws.com/tripdata`` bucket is public, no key). Large raw trip
files are git-ignored (§7.1); do not commit them.

    python -m pipelines.collectors.download_citibike 202406 202407
    python -m pipelines.collectors.download_citibike --from 202401 --to 202406 --extract
    python -m pipelines.collectors.download_citibike 202406 --jersey-city
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree

_ROOT = Path(__file__).resolve().parents[2]
_BUCKET = "https://s3.amazonaws.com/tripdata"
_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
_UA = {"User-Agent": "ShockFlowAI/1.0"}
_DEFAULT_DEST = _ROOT / "data" / "raw" / "citibike"


class CitiBikeDownloadUnavailable(RuntimeError):
    """Raised when the trip-data bucket cannot be reached (no network / blocked host)."""


def month_range(start: str, end: str) -> list[str]:
    """Inclusive list of ``YYYYMM`` strings from ``start`` to ``end``."""
    for mm in (start, end):
        if len(mm) != 6 or not mm.isdigit() or not 1 <= int(mm[4:]) <= 12:
            raise ValueError(f"month must be YYYYMM (01-12): {mm!r}")
    y0, m0 = int(start[:4]), int(start[4:])
    y1, m1 = int(end[:4]), int(end[4:])
    if (y0, m0) > (y1, m1):
        raise ValueError(f"--from {start} is after --to {end}")
    out: list[str] = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append(f"{y:04d}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def list_bucket_keys(*, timeout: int = 30) -> list[str]:
    """All object keys in the trip-data bucket (follows S3 list pagination)."""
    keys: list[str] = []
    marker = ""
    try:
        while True:
            url = f"{_BUCKET}/?marker={quote(marker)}" if marker else f"{_BUCKET}/"
            with urlopen(Request(url, headers=_UA), timeout=timeout) as r:  # noqa: S310
                root = ElementTree.fromstring(r.read())
            page = [
                k.text
                for c in root.findall(f"{_S3_NS}Contents")
                if (k := c.find(f"{_S3_NS}Key")) is not None and k.text
            ]
            keys.extend(page)
            truncated = (root.findtext(f"{_S3_NS}IsTruncated") or "false").lower() == "true"
            if not truncated or not page:
                break
            marker = page[-1]
    except OSError as exc:
        raise CitiBikeDownloadUnavailable(f"cannot reach {_BUCKET}: {exc}") from exc
    return keys


def find_keys_for_month(keys: list[str], month: str, *, jersey_city: bool = False) -> list[str]:
    """Trip-archive keys for a ``YYYYMM`` month (NYC by default, or the ``JC-`` variant)."""
    hits = []
    for k in keys:
        name = k.rsplit("/", 1)[-1]
        low = name.lower()
        if month not in name or "citibike" not in low or not low.endswith(".zip"):
            continue
        is_jc = low.startswith("jc-")
        if is_jc == jersey_city:
            hits.append(k)
    return sorted(hits)


def download_key(key: str, dest: Path, *, timeout: int = 300, overwrite: bool = False) -> Path:
    """Download one bucket key into ``dest`` (skips an existing file unless ``overwrite``)."""
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / key.rsplit("/", 1)[-1]
    if out.exists() and not overwrite:
        print(f"  skip (exists): {out.name}")
        return out
    url = f"{_BUCKET}/{quote(key)}"
    tmp = out.with_suffix(out.suffix + ".part")
    try:
        with urlopen(Request(url, headers=_UA), timeout=timeout) as r, tmp.open("wb") as f:  # noqa: S310
            shutil.copyfileobj(r, f)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise CitiBikeDownloadUnavailable(f"download failed for {key}: {exc}") from exc
    tmp.replace(out)
    print(f"  downloaded: {out.name} ({out.stat().st_size // 1024} KiB)")
    return out


def _extract(zip_path: Path) -> int:
    """Unzip CSVs next to the archive; returns the number of members extracted."""
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if not m.endswith("/") and "__MACOSX" not in m]
        zf.extractall(zip_path.parent, members)
    return len(members)


def download_months(
    months: list[str],
    dest: Path,
    *,
    jersey_city: bool = False,
    extract: bool = False,
    overwrite: bool = False,
) -> list[Path]:
    """Download every trip archive for the given months. Returns the saved archive paths."""
    keys = list_bucket_keys()
    saved: list[Path] = []
    for month in months:
        matches = find_keys_for_month(keys, month, jersey_city=jersey_city)
        if not matches:
            print(f"{month}: no matching archive in the bucket (check the month / --jersey-city)")
            continue
        for key in matches:
            path = download_key(key, dest, overwrite=overwrite)
            saved.append(path)
            if extract:
                n = _extract(path)
                print(f"    extracted {n} file(s)")
    return saved


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipelines.collectors.download_citibike")
    ap.add_argument("months", nargs="*", help="YYYYMM months, e.g. 202406 202407")
    ap.add_argument("--from", dest="from_month", default=None, help="range start YYYYMM")
    ap.add_argument("--to", dest="to_month", default=None, help="range end YYYYMM")
    ap.add_argument(
        "--dest", default=str(_DEFAULT_DEST), help="output dir (default data/raw/citibike)"
    )
    ap.add_argument("--jersey-city", action="store_true", help="download the JC- variant instead")
    ap.add_argument("--extract", action="store_true", help="unzip the CSVs next to each archive")
    ap.add_argument("--overwrite", action="store_true", help="re-download even if the file exists")
    args = ap.parse_args(argv)

    months = list(args.months)
    if args.from_month and args.to_month:
        months = month_range(args.from_month, args.to_month)
    if not months:
        ap.error("give one or more YYYYMM months, or --from YYYYMM --to YYYYMM")

    dest = Path(args.dest)
    print(f"Citi Bike trip download -> {dest}  (months: {', '.join(months)})")
    try:
        saved = download_months(
            months,
            dest,
            jersey_city=args.jersey_city,
            extract=args.extract,
            overwrite=args.overwrite,
        )
    except CitiBikeDownloadUnavailable as exc:
        print(f"download unavailable: {exc}")
        print("Needs outbound network to s3.amazonaws.com/tripdata. Retry where egress is allowed.")
        return 1

    if not saved:
        return 1
    print(f"\nDone. {len(saved)} archive(s) in {dest}.")
    print("Next: python -m ml.forecasting.run <that .zip> --news <news.jsonl> --provider anthropic")
    return 0


if __name__ == "__main__":
    sys.exit(main())
