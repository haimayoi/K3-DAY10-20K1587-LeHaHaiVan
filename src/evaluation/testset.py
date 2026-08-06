from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json


REQUIRED_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "published",
}
MAX_DOCUMENTS = 3


def _non_empty(value: Any) -> str:
    return normalize_whitespace("" if pd.isna(value) else str(value))


def build_test_set(df: pd.DataFrame, output_path: Path) -> list[dict[str, Any]]:
    """Build a deterministic, factual test set from actual cleaned documents.

    Every question quotes its title, enabling the QA layer's exact lookup. The
    ground-truth document ID therefore always comes directly from ``paper_id``
    in the supplied cleaned dataset.
    """
    missing_columns = REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing required columns: {sorted(missing_columns)}")
    if df.empty:
        raise ValueError("Cannot build an evaluation set from an empty cleaned dataframe.")

    samples: list[dict[str, Any]] = []
    selected = df.sort_values("paper_id", kind="stable").head(MAX_DOCUMENTS)
    for row in selected.to_dict(orient="records"):
        paper_id = _non_empty(row["paper_id"])
        title = _non_empty(row["title"])
        summary = _non_empty(row["summary"])
        authors = _non_empty(row["authors_joined"])
        published = _non_empty(row["published"])
        categories = _non_empty(row["categories_joined"])
        if not paper_id or not title or not summary or not published:
            continue

        ground_truth_doc_ids = [paper_id]
        questions = [
            ("summary", f"What is the main idea of '{title}'?", first_sentence(summary)),
            ("date", f"When was '{title}' published on?", published),
        ]
        if authors:
            questions.append(("authors", f"Who authored '{title}'?", authors))
        if categories:
            questions.append(("categories", f"What categories does '{title}' belong to?", categories))

        for question_type, question, ground_truth in questions:
            samples.append(
                {
                    "id": f"{paper_id}-{question_type}",
                    "question_type": question_type,
                    "question": question,
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": ground_truth_doc_ids,
                }
            )

    if not samples:
        raise ValueError("No valid cleaned records were available to build the evaluation set.")
    write_json(Path(output_path), samples)
    return samples
