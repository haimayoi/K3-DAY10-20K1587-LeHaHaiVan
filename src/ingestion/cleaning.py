from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

MIN_TITLE_LENGTH = 3
MIN_SUMMARY_LENGTH = 20

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "age_days",
    "summary_chars",
    "text_for_embedding",
]


def _parse_published_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang de embed.

    1. Normalize title, summary, authors, categories.
    2. Parse published date; loai record thieu/khong parse duoc date.
    3. Tinh age_days tu run_date.
    4. Tao cot helper: authors_joined, categories_joined, summary_chars, text_for_embedding.
    5. Drop duplicate paper_id va filter row xau (title/summary rong hoac qua ngan).
    6. Sort theo published giam dan va return.

    Reason va count cho moi record bi loai duoc ghi vao `df.attrs["dropped_reasons"]"
    (khong doi signature ham nen day la cach duy nhat truyen log nay ra ngoai).
    """
    rows: list[dict] = []
    dropped_reasons = {
        "missing_or_too_short_title": 0,
        "missing_or_too_short_summary": 0,
        "missing_or_unparseable_published_date": 0,
    }

    for record in records:
        title = normalize_whitespace(record.title)
        summary = normalize_whitespace(record.summary)
        published_date = _parse_published_date(record.published)

        if len(title) < MIN_TITLE_LENGTH:
            dropped_reasons["missing_or_too_short_title"] += 1
            continue
        if len(summary) < MIN_SUMMARY_LENGTH:
            dropped_reasons["missing_or_too_short_summary"] += 1
            continue
        if published_date is None:
            dropped_reasons["missing_or_unparseable_published_date"] += 1
            continue

        age_days = max(0, (run_date.date() - published_date).days)
        text_for_embedding = normalize_whitespace(f"{title}. {summary}")

        rows.append(
            {
                "paper_id": record.paper_id,
                "title": title,
                "summary": summary,
                "authors_joined": compact_join(author.strip() for author in record.authors),
                "categories_joined": compact_join(category.strip() for category in record.categories),
                "primary_category": normalize_whitespace(record.primary_category),
                "published": published_date.isoformat(),
                "updated": record.updated,
                "abs_url": record.abs_url,
                "pdf_url": record.pdf_url,
                "age_days": age_days,
                "summary_chars": len(summary),
                "text_for_embedding": text_for_embedding,
            }
        )

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)

    rows_before_dedupe = len(df)
    df = df.drop_duplicates(subset="paper_id", keep="first").reset_index(drop=True)
    dropped_reasons["duplicate_paper_id"] = rows_before_dedupe - len(df)

    df = df.sort_values("published", ascending=False).reset_index(drop=True)

    df.attrs["source_record_count"] = len(records)
    df.attrs["clean_record_count"] = len(df)
    df.attrs["dropped_reasons"] = dropped_reasons

    return df
