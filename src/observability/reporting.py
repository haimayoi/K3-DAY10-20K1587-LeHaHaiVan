from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import write_text


METRIC_NAMES = ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score")


def _display(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, bool):
        return "Pass" if value else "Fail"
    return str(value)


def _markdown_table(rows: list[tuple[str, Any]]) -> str:
    lines = ["| Item | Value |", "| --- | --- |"]
    lines.extend(f"| {key} | {_display(value)} |" for key, value in rows)
    return "\n".join(lines)


def _numeric_delta(later: Any, earlier: Any) -> float | int | None:
    """Return a delta only for real numeric measurements, not status booleans."""
    if isinstance(later, bool) or isinstance(earlier, bool):
        return None
    if isinstance(later, (int, float)) and isinstance(earlier, (int, float)):
        return later - earlier
    return None

def _failed_checks(quality: dict[str, Any] | None) -> str:
    if quality is None:
        return "N/A"
    failed = [name for name, check in quality.get("checks", {}).items() if not check.get("passed")]
    return ", ".join(failed) if failed else "None"


def generate_phase1_report(
    report_path: Path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a baseline report from the artifacts produced by the pipeline."""
    quality_checks = quality.get("checks", {})
    quality_rows = [(name, "Pass" if check.get("passed") else "Fail") for name, check in quality_checks.items()]
    sections = [
        "# Phase 1 Baseline Report",
        "## Source",
        _markdown_table(list(source_summary.items())),
        "## Evaluation Metrics",
        _markdown_table([(name, metrics.get(name)) for name in METRIC_NAMES] + [("samples", metrics.get("samples"))]),
        "## Data Quality",
        f"Overall status: **{'Pass' if quality.get('passed') else 'Fail'}**",
        _markdown_table(quality_rows),
        "## Freshness",
        _markdown_table(
            [
                ("is_fresh", freshness.get("is_fresh")),
                ("latest_published", freshness.get("latest_published")),
                ("oldest_published", freshness.get("oldest_published")),
                ("stale_rows", freshness.get("stale_rows")),
                ("total_rows", freshness.get("total_rows")),
                ("freshness_threshold_days", freshness.get("freshness_threshold_days")),
            ]
        ),
        "## Ragas",
        f"```json\n{metrics.get('ragas', {})}\n```",
    ]
    write_text(Path(report_path), "\n\n".join(sections) + "\n")


def generate_corruption_report(
    report_path: Path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
) -> None:
    """Write an evidence-backed baseline/corrupted/repaired comparison report."""
    metric_rows = []
    for name in METRIC_NAMES:
        baseline = baseline_metrics.get(name)
        corrupted = corrupted_metrics.get(name)
        repaired = repaired_metrics.get(name)
        metric_rows.append((name, baseline, corrupted, repaired, _numeric_delta(corrupted, baseline), _numeric_delta(repaired, corrupted)))
    baseline_quality = baseline_quality or {}
    baseline_freshness = baseline_freshness or {}
    signal_rows = [
        ("Quality passed", baseline_quality.get("passed"), corrupted_quality.get("passed"), repaired_quality.get("passed")),
        ("Failed quality checks", _failed_checks(baseline_quality), _failed_checks(corrupted_quality), _failed_checks(repaired_quality)),
        ("Row count", baseline_quality.get("row_count"), corrupted_quality.get("row_count"), repaired_quality.get("row_count")),
        ("Fresh", baseline_freshness.get("is_fresh"), corrupted_freshness.get("is_fresh"), repaired_freshness.get("is_fresh")),
        ("Stale rows", baseline_freshness.get("stale_rows"), corrupted_freshness.get("stale_rows"), repaired_freshness.get("stale_rows")),
        ("Missing published dates", baseline_freshness.get("missing_published"), corrupted_freshness.get("missing_published"), repaired_freshness.get("missing_published")),
        ("Invalid age days", baseline_freshness.get("invalid_age_days"), corrupted_freshness.get("invalid_age_days"), repaired_freshness.get("invalid_age_days")),
    ]
    lines = [
        "# Corruption and Repair Comparison",
        "## Evaluation Metrics",
        "| Metric | Baseline | Corrupted | Repaired | Corrupted - Baseline | Repaired - Corrupted |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {name} | {_display(baseline)} | {_display(corrupted)} | {_display(repaired)} | {_display(delta)} | {_display(recovery)} |"
        for name, baseline, corrupted, repaired, delta, recovery in metric_rows
    )
    lines.extend([
        "",
        "## Data Quality and Freshness",
        "| Signal | Baseline | Corrupted | Repaired | Corrupted - Baseline | Repaired - Corrupted |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    lines.extend(
        f"| {name} | {_display(baseline)} | {_display(corrupted)} | {_display(repaired)} | {_display(_numeric_delta(corrupted, baseline))} | {_display(_numeric_delta(repaired, corrupted))} |"
        for name, baseline, corrupted, repaired in signal_rows
    )
    lines.extend([
        "",
        "All comparisons use the same fixed evaluation set. Interpret recovery only from the values above and their linked artifacts.",
    ])
    write_text(Path(report_path), "\n".join(lines) + "\n")
