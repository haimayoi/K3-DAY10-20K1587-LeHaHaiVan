from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import normalize_whitespace, write_json


REQUIRED_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "published",
    "age_days",
    "summary_chars",
    "text_for_embedding",
}
RECORDS_PER_CORRUPTION = 2
NOISE_PREFIX = "CORRUPTED NOISE: unrelated boilerplate alpha beta gamma."
TRUNCATED_TITLE_CHARS = 12
STALE_PUBLISHED = "2000-01-01"
STALE_AGE_DAYS = 10_000


def _event(
    corruption_type: str,
    record_ids: list[str],
    parameters: dict[str, Any],
    before_count: int,
    after_count: int,
    changes: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "corruption_type": corruption_type,
        "record_ids": record_ids,
        "parameters": parameters,
        "before_count": before_count,
        "after_count": after_count,
        "changes": changes,
    }


def _target_indices(df: pd.DataFrame, offset: int) -> list[int]:
    ordered = df.sort_values("paper_id", kind="stable").index.tolist()
    return ordered[offset : offset + RECORDS_PER_CORRUPTION]


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path: Path) -> pd.DataFrame:
    """Apply deterministic data corruptions and write record-level evidence."""
    missing_columns = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing required columns: {missing_columns}")
    if len(df) < 10:
        raise ValueError("At least 10 clean records are required to apply all corruption scenarios.")

    corrupted = df.copy(deep=True).reset_index(drop=True)
    source_count = len(corrupted)
    events: list[dict[str, Any]] = []

    published = pd.to_datetime(corrupted["published"], errors="coerce")
    if published.notna().sum() < RECORDS_PER_CORRUPTION:
        raise ValueError("Not enough valid published dates to drop latest records.")
    latest_indices = published.sort_values(ascending=False).index[:RECORDS_PER_CORRUPTION]
    latest_rows = corrupted.loc[latest_indices, ["paper_id", "published"]]
    before_count = len(corrupted)
    corrupted = corrupted.drop(index=latest_indices).reset_index(drop=True)
    events.append(
        _event(
            "drop_latest_records",
            latest_rows["paper_id"].astype(str).tolist(),
            {"count": RECORDS_PER_CORRUPTION, "order_by": "published", "ascending": False},
            before_count,
            len(corrupted),
            [
                {"paper_id": str(row.paper_id), "published": str(row.published)}
                for row in latest_rows.itertuples(index=False)
            ],
        )
    )

    blank_indices = _target_indices(corrupted, 0)
    blank_changes = []
    for index in blank_indices:
        paper_id = str(corrupted.at[index, "paper_id"])
        before_chars = len(str(corrupted.at[index, "summary"]))
        corrupted.at[index, "summary"] = ""
        blank_changes.append(
            {"paper_id": paper_id, "before_summary_chars": before_chars, "after_summary_chars": 0}
        )
    events.append(
        _event(
            "blank_summary",
            [change["paper_id"] for change in blank_changes],
            {"field": "summary", "replacement": ""},
            len(corrupted),
            len(corrupted),
            blank_changes,
        )
    )

    noise_indices = _target_indices(corrupted, 2)
    noise_changes = []
    for index in noise_indices:
        paper_id = str(corrupted.at[index, "paper_id"])
        before_summary = str(corrupted.at[index, "summary"])
        corrupted.at[index, "summary"] = f"{NOISE_PREFIX} {before_summary}"
        noise_changes.append(
            {
                "paper_id": paper_id,
                "before_summary_chars": len(before_summary),
                "after_summary_chars": len(str(corrupted.at[index, "summary"])),
            }
        )
    events.append(
        _event(
            "add_summary_noise",
            [change["paper_id"] for change in noise_changes],
            {"field": "summary", "prefix": NOISE_PREFIX},
            len(corrupted),
            len(corrupted),
            noise_changes,
        )
    )

    title_indices = _target_indices(corrupted, 4)
    title_changes = []
    for index in title_indices:
        paper_id = str(corrupted.at[index, "paper_id"])
        original_title = str(corrupted.at[index, "title"])
        truncated_title = original_title[:TRUNCATED_TITLE_CHARS]
        corrupted.at[index, "title"] = truncated_title
        title_changes.append(
            {"paper_id": paper_id, "before": original_title, "after": truncated_title}
        )
    events.append(
        _event(
            "truncate_title",
            [change["paper_id"] for change in title_changes],
            {"field": "title", "max_chars": TRUNCATED_TITLE_CHARS},
            len(corrupted),
            len(corrupted),
            title_changes,
        )
    )

    stale_indices = _target_indices(corrupted, 6)
    stale_changes = []
    for index in stale_indices:
        paper_id = str(corrupted.at[index, "paper_id"])
        stale_changes.append(
            {
                "paper_id": paper_id,
                "before_published": str(corrupted.at[index, "published"]),
                "after_published": STALE_PUBLISHED,
                "before_age_days": int(corrupted.at[index, "age_days"]),
                "after_age_days": STALE_AGE_DAYS,
            }
        )
        corrupted.at[index, "published"] = STALE_PUBLISHED
        corrupted.at[index, "age_days"] = STALE_AGE_DAYS
    events.append(
        _event(
            "make_publication_stale",
            [change["paper_id"] for change in stale_changes],
            {"published": STALE_PUBLISHED, "age_days": STALE_AGE_DAYS},
            len(corrupted),
            len(corrupted),
            stale_changes,
        )
    )

    duplicate_indices = _target_indices(corrupted, 0)
    duplicate_rows = corrupted.loc[duplicate_indices].copy(deep=True)
    before_count = len(corrupted)
    corrupted = pd.concat([corrupted, duplicate_rows], ignore_index=True)
    duplicate_ids = duplicate_rows["paper_id"].astype(str).tolist()
    events.append(
        _event(
            "add_duplicate_rows",
            duplicate_ids,
            {"count": len(duplicate_rows), "duplicate_key": "paper_id"},
            before_count,
            len(corrupted),
            [{"paper_id": paper_id, "copies_added": 1} for paper_id in duplicate_ids],
        )
    )

    corrupted["summary"] = corrupted["summary"].fillna("").astype(str)
    corrupted["title"] = corrupted["title"].fillna("").astype(str)
    corrupted["summary_chars"] = corrupted["summary"].str.len()
    corrupted["text_for_embedding"] = [
        normalize_whitespace(f"{title}. {summary}")
        for title, summary in zip(corrupted["title"], corrupted["summary"], strict=True)
    ]
    corrupted = corrupted.reset_index(drop=True)

    log = {
        "schema_version": 1,
        "source_count": source_count,
        "final_count": len(corrupted),
        "corruption_types": [event["corruption_type"] for event in events],
        "events": events,
    }
    write_json(Path(output_log_path), log)
    corrupted.attrs["corruption_log"] = log
    return corrupted
