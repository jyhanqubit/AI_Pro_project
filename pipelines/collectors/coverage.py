"""News/event coverage report + coverage gate (V1_Prompt §7).

The report carries the §7 artifact fields. At backfill time (V1-01) only the article-level fields
are populated; event-cluster / zone-hour / non-zero-feature-ratio fields are filled once extraction
and features run (V1-02+) and are left null here rather than fabricated. The gate decides whether
the accuracy claim may be enabled; a gate failure never rewrites data (§7).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .backfill import BackfillReport


@dataclass
class CoverageReport:
    raw_article_count: int
    candidate_article_count: int
    accepted_count: int
    quarantined_count: int
    rejected_count: int
    unique_source_count: int
    source_distribution: dict[str, int]
    # Filled in V1-02+ (extraction/features); null/0 at backfill time (not fabricated).
    unique_event_cluster_count: int | None = None
    event_type_distribution: dict[str, int] | None = None
    affected_zone_hour_count: int | None = None
    non_zero_feature_ratio_by_split: dict[str, float] | None = None
    degraded: bool = False
    degraded_reason: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def coverage_report(backfill: BackfillReport) -> CoverageReport:
    return CoverageReport(
        raw_article_count=backfill.raw_count,
        candidate_article_count=backfill.candidate_count,
        accepted_count=backfill.accepted_count,
        quarantined_count=0,  # article-level backfill has no quarantine; extraction (V1-02) does
        rejected_count=sum(backfill.excluded.values()),
        unique_source_count=backfill.unique_sources,
        source_distribution=backfill.source_distribution,
        degraded=backfill.degraded,
        degraded_reason=backfill.degraded_reason,
    )


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def coverage_gate(report: CoverageReport, config) -> GateResult:
    """Pass/fail the coverage gate. On failure the accuracy claim stays disabled (§7)."""
    reasons: list[str] = []
    if report.degraded:
        reasons.append(f"provider degraded: {report.degraded_reason}")
    if report.accepted_count < config.min_accepted_articles:
        reasons.append(
            f"accepted {report.accepted_count} < min {config.min_accepted_articles}"
        )
    if report.unique_source_count < config.min_unique_sources:
        reasons.append(
            f"unique sources {report.unique_source_count} < min {config.min_unique_sources}"
        )
    ratio = (
        report.candidate_article_count / report.raw_article_count
        if report.raw_article_count
        else 0.0
    )
    if ratio < config.min_ontology_match_ratio:
        reasons.append(
            f"candidate ratio {ratio:.2f} < min {config.min_ontology_match_ratio}"
        )
    return GateResult(passed=not reasons, reasons=reasons)
