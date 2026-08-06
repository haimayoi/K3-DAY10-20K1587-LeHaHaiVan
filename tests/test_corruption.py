from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from ingestion.corruption import corrupt_clean_dataframe


def _clean_dataframe(rows: int = 12) -> pd.DataFrame:
    latest = date(2026, 8, 1)
    records = []
    for index in range(rows):
        title = f"Paper title {index:02d}"
        summary = f"Summary for paper {index:02d} with enough text for corruption testing."
        records.append(
            {
                "paper_id": f"paper-{index:02d}",
                "title": title,
                "summary": summary,
                "published": (latest - timedelta(days=index)).isoformat(),
                "age_days": index,
                "summary_chars": len(summary),
                "text_for_embedding": f"{title}. {summary}",
            }
        )
    return pd.DataFrame(records)


class CorruptionTests(unittest.TestCase):
    def test_applies_all_scenarios_and_logs_evidence(self) -> None:
        clean = _clean_dataframe()
        original = clean.copy(deep=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "corruption_log.json"
            corrupted = corrupt_clean_dataframe(clean, log_path)
            log = json.loads(log_path.read_text(encoding="utf-8"))

        pd.testing.assert_frame_equal(clean, original)
        self.assertEqual(len(corrupted), len(clean))
        self.assertEqual(log["source_count"], len(clean))
        self.assertEqual(log["final_count"], len(corrupted))
        self.assertEqual(
            log["corruption_types"],
            [
                "drop_latest_records",
                "blank_summary",
                "add_summary_noise",
                "truncate_title",
                "make_publication_stale",
                "add_duplicate_rows",
            ],
        )
        self.assertTrue(all(event["record_ids"] for event in log["events"]))
        self.assertTrue(all("parameters" in event for event in log["events"]))
        self.assertTrue(
            all("before_count" in event and "after_count" in event for event in log["events"])
        )
        self.assertFalse({"paper-00", "paper-01"} & set(corrupted["paper_id"]))
        self.assertGreaterEqual(int(corrupted["summary"].eq("").sum()), 2)
        self.assertGreaterEqual(
            int(corrupted["summary"].str.startswith("CORRUPTED NOISE").sum()), 2
        )
        self.assertGreaterEqual(int(corrupted["title"].str.len().eq(12).sum()), 2)
        self.assertGreaterEqual(int(corrupted["published"].eq("2000-01-01").sum()), 2)
        self.assertGreaterEqual(int(corrupted["paper_id"].duplicated(keep=False).sum()), 4)
        self.assertTrue(
            all(
                text == f"{title}. {summary}".strip()
                for text, title, summary in zip(
                    corrupted["text_for_embedding"],
                    corrupted["title"],
                    corrupted["summary"],
                    strict=True,
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
