from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import safe_slug, write_json


def _missing_count(df: pd.DataFrame, column: str) -> int:
    """Count null or whitespace-only values without changing the dataframe."""
    if column not in df.columns:
        return len(df)
    values = df[column]
    return int((values.isna() | values.fillna("").astype(str).str.strip().eq("")).sum())


def _check(passed: bool, **details: Any) -> dict[str, Any]:
    return {"passed": passed, **details}


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Validate the cleaned-paper contract and write a JSON quality artifact.

    The checks deliberately report counts rather than silently dropping bad rows.
    This makes baseline, corrupted, and repaired datasets directly comparable.
    """
    row_count = len(df)
    paper_id_missing = _missing_count(df, "paper_id")
    title_missing = _missing_count(df, "title")
    summary_missing = _missing_count(df, "summary")
    duplicate_paper_id_rows = (
        int(df["paper_id"].fillna("").astype(str).str.strip().duplicated(keep=False).sum())
        if "paper_id" in df.columns
        else row_count
    )
    duplicate_rows = int(df.duplicated().sum())
    invalid_age_days = (
        int(pd.to_numeric(df["age_days"], errors="coerce").isna().sum())
        if "age_days" in df.columns
        else row_count
    )

    checks = {
        "row_count": _check(row_count > 0, value=row_count, minimum=1),
        "paper_id_not_null": _check(paper_id_missing == 0, missing=paper_id_missing),
        "paper_id_unique": _check(duplicate_paper_id_rows == 0, duplicate_rows=duplicate_paper_id_rows),
        "title_not_null": _check(title_missing == 0, missing=title_missing),
        "summary_not_null": _check(summary_missing == 0, missing=summary_missing),
        "duplicate_rows": _check(duplicate_rows == 0, duplicate_rows=duplicate_rows),
        "age_days_valid": _check(invalid_age_days == 0, invalid=invalid_age_days),
    }
    result = {
        "report_name": report_name,
        "row_count": row_count,
        "checks": checks,
        "passed": all(check["passed"] for check in checks.values()),
    }

    report_path = settings.paths.quality_dir / f"{safe_slug(report_name)}.json"
    write_json(report_path, result)
    return result


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path: Path) -> dict[str, Any]:
    """Summarize freshness from the cleaned dataset's real dates and ``age_days``.

    ``age_days`` is created by cleaning, so this function never recalculates it
    against a new wall-clock date. That keeps the report reproducible.
    """
    total_rows = len(df)
    published = (
        pd.to_datetime(df["published"], errors="coerce", utc=True)
        if "published" in df.columns
        else pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    )
    ages = (
        pd.to_numeric(df["age_days"], errors="coerce")
        if "age_days" in df.columns
        else pd.Series(float("nan"), index=df.index, dtype="float64")
    )
    valid_published = published.dropna()
    stale_rows = int((ages > settings.freshness_threshold_days).fillna(False).sum())
    missing_published = int(published.isna().sum())
    invalid_age_days = int(ages.isna().sum())

    result = {
        "latest_published": valid_published.max().date().isoformat() if not valid_published.empty else None,
        "oldest_published": valid_published.min().date().isoformat() if not valid_published.empty else None,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "missing_published": missing_published,
        "invalid_age_days": invalid_age_days,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "is_fresh": total_rows > 0 and stale_rows == 0 and missing_published == 0 and invalid_age_days == 0,
    }
    write_json(Path(report_path), result)
    return result
