from __future__ import annotations

from dataclasses import asdict, dataclass
import html
from pathlib import Path
import re
import time

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, safe_slug, write_json

CROSSREF_API_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 503}
MAX_ATTEMPTS = 5
INITIAL_BACKOFF_SECONDS = 1.0

_JATS_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _clean_abstract(raw_abstract: str) -> str:
    """Crossref abstracts are wrapped in JATS XML tags (e.g. <jats:p>...</jats:p>)
    and contain HTML/XML entities (e.g. &lt;, &amp;) that need decoding."""
    without_tags = _JATS_TAG_RE.sub(" ", raw_abstract or "")
    return normalize_whitespace(html.unescape(without_tags))


def _extract_date(item: dict) -> str:
    """Pick the most reliable publication date and normalize it to YYYY-MM-DD."""
    for key in ("published", "published-print", "published-online", "issued", "created"):
        node = item.get(key)
        if not node:
            continue
        parts = node.get("date-parts")
        if not parts or not parts[0]:
            continue
        date_parts = parts[0]
        year = date_parts[0]
        month = date_parts[1] if len(date_parts) > 1 else 1
        day = date_parts[2] if len(date_parts) > 2 else 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    return ""


def _extract_authors(item: dict) -> list[str]:
    authors = []
    for author in item.get("author") or []:
        name = compact_author_name(author)
        if name:
            authors.append(name)
    return authors


def compact_author_name(author: dict) -> str:
    given = normalize_whitespace(author.get("given", ""))
    family = normalize_whitespace(author.get("family", ""))
    full_name = " ".join(part for part in (given, family) if part)
    return full_name or normalize_whitespace(author.get("name", ""))


def _extract_categories(item: dict) -> tuple[list[str], str]:
    subjects = [normalize_whitespace(s) for s in (item.get("subject") or []) if normalize_whitespace(s)]
    if subjects:
        return subjects, subjects[0]
    containers = [normalize_whitespace(c) for c in (item.get("container-title") or []) if normalize_whitespace(c)]
    if containers:
        return containers, containers[0]
    return [], ""


def _extract_pdf_url(item: dict) -> str:
    for link in item.get("link") or []:
        if link.get("content-type") == "application/pdf" and link.get("URL"):
            return link["URL"]
    return ""


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list PaperRecord.

    1. Duyet payload["message"]["items"].
    2. Lay DOI, title, abstract, authors, subject, dates, URLs.
    3. Chuan hoa text va bo record khong co DOI/title (khong the tao stable ID).
    4. Tra ve list PaperRecord.
    """
    items = (payload.get("message") or {}).get("items") or []
    records: list[PaperRecord] = []

    for item in items:
        doi = normalize_whitespace(item.get("DOI", ""))
        titles = item.get("title") or []
        title = normalize_whitespace(html.unescape(titles[0])) if titles else ""

        if not doi or not title:
            continue

        categories, primary_category = _extract_categories(item)

        records.append(
            PaperRecord(
                paper_id=safe_slug(doi),
                title=title,
                summary=_clean_abstract(item.get("abstract", "")),
                authors=_extract_authors(item),
                categories=categories,
                primary_category=primary_category,
                published=_extract_date(item),
                updated=(item.get("indexed") or {}).get("date-time", "")
                or (item.get("created") or {}).get("date-time", ""),
                abs_url=normalize_whitespace(item.get("URL", "")) or f"https://doi.org/{doi}",
                pdf_url=_extract_pdf_url(item),
                comment=normalize_whitespace(item.get("type", "")),
            )
        )

    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi Crossref API, luu raw response, parse thanh records va luu lai.

    1. Tao params tu settings.source_query, settings.source_filter, settings.max_results.
    2. Goi API voi retry/backoff cho 429/503.
    3. Luu raw response vao settings.paths.raw_api_response.
    4. Parse payload bang parse_crossref_payload.
    5. Luu records vao settings.paths.raw_records_json.
    """
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }
    headers = {"User-Agent": "day10-data-pipeline-lab/1.0 (mailto:student@example.com)"}

    last_error: Exception | None = None
    response = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(CROSSREF_API_URL, params=params, headers=headers, timeout=30)
        except requests.RequestException as exc:
            last_error = exc
        else:
            if response.status_code not in RETRYABLE_STATUS_CODES:
                break
            last_error = requests.HTTPError(f"Retryable status {response.status_code} from Crossref")

        if attempt < MAX_ATTEMPTS:
            time.sleep(INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)))

    if response is None:
        raise RuntimeError(f"Failed to reach Crossref API after {MAX_ATTEMPTS} attempts: {last_error}")
    if response.status_code in RETRYABLE_STATUS_CODES:
        raise RuntimeError(
            f"Crossref API still returning {response.status_code} after {MAX_ATTEMPTS} attempts."
        )
    response.raise_for_status()

    payload = response.json()
    write_json(settings.paths.raw_api_response, payload)

    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot da luu va map thanh PaperRecord."""
    raw_items = read_json(path)
    return [PaperRecord(**item) for item in raw_items]
