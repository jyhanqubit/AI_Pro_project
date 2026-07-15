"""Build the offline search corpus. CLAUDE.md §12; V2-03.

Indexes the five demo stations (with geo) from the gazetteer, plus a small help corpus, into
``SearchDoc``s. Static place/help metadata only — no live inventory (that is re-hydrated from the
operational store at query time).
"""

from __future__ import annotations

import json

from config.collectors import REBALANCING_DEMO_FIXTURE, STATION_GAZETTEER_FIXTURE

from .provider import SearchDoc

# A tiny help index (help_v2) so non-station queries (요금/반납 등) have somewhere to route.
_HELP_DOCS: tuple[tuple[str, str, str], ...] = (
    (
        "help_pricing",
        "요금 · 할증 정책",
        "요금 가격 할증 surge pricing 부족 크레딧 나이트 정책 요금제 how much price fare",
    ),
    (
        "help_return",
        "자전거 반납 방법",
        "반납 거치대 도크 dock return 반납하기 어디에 반납 빈 도크 자리",
    ),
    (
        "help_ebike",
        "전기자전거 이용",
        "전기자전거 이바이크 ebike electric 배터리 충전 속도 e-bike",
    ),
    (
        "help_membership",
        "멤버십 · 언락",
        "멤버십 회원 비회원 언락 unlock membership 요금제 구독 가입",
    ),
)


def build_corpus() -> list[SearchDoc]:
    """Station docs (with lat/lng from the rebalancing fixture) + the help docs."""
    gaz = json.loads(STATION_GAZETTEER_FIXTURE.read_text(encoding="utf-8"))["stations"]
    coords = {
        str(s["station_id"]): (float(s["lat"]), float(s["lng"]))
        for s in json.loads(REBALANCING_DEMO_FIXTURE.read_text(encoding="utf-8"))["stations"]
    }

    docs: list[SearchDoc] = []
    for s in gaz:
        sid = str(s["station_id"])
        lat, lng = coords.get(sid, (None, None))
        text = " ".join([s["ko"], s["en"], s["area"], sid, *[str(a) for a in s.get("aliases", [])]])
        docs.append(
            SearchDoc(
                doc_id=f"station:{sid}",
                kind="station",
                title=s["ko"],
                text=text,
                station_id=sid,
                lat=lat,
                lng=lng,
            )
        )
    for doc_id, title, text in _HELP_DOCS:
        docs.append(SearchDoc(doc_id=doc_id, kind="help", title=title, text=f"{title} {text}"))
    return docs
