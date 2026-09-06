"""Section-first, offline RAG evidence utilities.

This module never calls AWS. It derives bounded records from the checked-in Ontario Parks
snapshot and optionally supports a local sentence-transformers model in the demo script.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data/rag/ontario-provincial-parks-guide.md"
STOP = {"a", "an", "and", "are", "based", "does", "for", "have", "i", "in", "is", "list", "me", "of", "on", "the", "to", "what", "which", "where", "with"}
GENERIC_PARK_TERMS = {"ontario", "provincial", "park", "parks"}
CURRENT_STATUS_PATTERN = re.compile(r"\b(?:today|tomorrow|this weekend|current|currently|open|available|availability|hours|prices?|closure|closed|fire ban|reserve|reservation|reservations)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SectionRecord:
    record_id: str
    park_name: str
    section: str
    source_url: str
    source_as_of: str
    text: str


@dataclass(frozen=True)
class SectionHit:
    record_id: str
    park_name: str
    section: str
    source_url: str
    source_as_of: str
    score: float
    text: str


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _terms(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", value.casefold()) if len(word) > 2 and word not in STOP}


def _park_filter(question: str, parks: Iterable[str]) -> str | None:
    lowered = question.casefold()
    exact = [park for park in parks if park.casefold() in lowered]
    if exact:
        return max(exact, key=len)
    if re.search(r"\b[A-Z][A-Za-z0-9'/-]*(?:\s+[A-Z][A-Za-z0-9'/-]*){0,3}\s+Park\b", question):
        return "__unknown__"
    return None


def load_section_records(path: Path = CORPUS) -> list[SectionRecord]:
    """Return one record per meaningful park section in the static snapshot."""
    text = path.read_text(encoding="utf-8")
    records: list[SectionRecord] = []
    for block in re.split(r"(?=^##\s+)", text, flags=re.MULTILINE):
        heading = re.match(r"##\s+([^\n]+)", block)
        url = re.search(r"https://www\.ontarioparks\.ca/park/[A-Za-z0-9-]+", block)
        snapshot = re.search(r"source captured (\d{4}-\d{2}-\d{2})", block)
        if not heading or not url:
            continue
        park = heading.group(1).strip()
        source_as_of = snapshot.group(1) if snapshot else "unknown"
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        section_lines = {
            "Activities": [line for line in lines if line.startswith("- Activities listed:")],
            "Facilities": [line for line in lines if line.startswith("- Relevant facilities/rentals listed:")],
        }
        for section, selected in section_lines.items():
            if not selected:
                continue
            record_id = f"{_slug(park)}.{section.casefold()}"
            records.append(SectionRecord(record_id, park, section, url.group(0), source_as_of, f"{park}\n{section}\n{selected[0]}"))
    return records


def split_section(record: SectionRecord, max_tokens: int = 300, overlap_tokens: int = 0) -> list[SectionRecord]:
    """Split only oversized sections, preserving the parent identity in every child."""
    if max_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("max_tokens must be positive and overlap_tokens must be smaller")
    words = record.text.split()
    if len(words) <= max_tokens:
        return [record]
    step = max_tokens - overlap_tokens
    chunks: list[SectionRecord] = []
    for index, start in enumerate(range(0, len(words), step)):
        excerpt = " ".join(words[start:start + max_tokens])
        if not excerpt:
            continue
        chunks.append(SectionRecord(f"{record.record_id}.{index:02d}", record.park_name, record.section, record.source_url, record.source_as_of, excerpt))
    return chunks


def section_chunks(path: Path = CORPUS, max_tokens: int = 300, overlap_tokens: int = 0) -> list[SectionRecord]:
    chunks: list[SectionRecord] = []
    for record in load_section_records(path):
        chunks.extend(split_section(record, max_tokens, overlap_tokens))
    return chunks


def corpus_profile(records: list[SectionRecord]) -> dict[str, int]:
    parks = {record.park_name for record in records}
    activities = sum(record.section == "Activities" for record in records)
    facilities = sum(record.section == "Facilities" for record in records)
    missing_source_dates = sum(record.source_as_of == "unknown" for record in records)
    headings = re.findall(r"^##\s+([^\n]+)", CORPUS.read_text(encoding="utf-8"), flags=re.MULTILINE)
    total_parks = len([heading for heading in headings if heading.casefold() != "coverage"])
    return {
        "snapshot_park_records": total_parks,
        "parks_with_sections": len(parks),
        "parks_without_primary_sections": max(0, total_parks - len(parks)),
        "section_records": len(records),
        "activity_sections": activities,
        "facility_sections": facilities,
        "missing_source_dates": missing_source_dates,
    }


def current_status_question(question: str) -> bool:
    return bool(CURRENT_STATUS_PATTERN.search(question))


def records_for_question(question: str, records: list[SectionRecord]) -> list[SectionRecord]:
    park_filter = _park_filter(question, {record.park_name for record in records})
    if park_filter == "__unknown__":
        return []
    if park_filter:
        return [record for record in records if record.park_name == park_filter]
    return records


def lexical_search(question: str, records: list[SectionRecord], top_k: int = 3) -> list[SectionHit]:
    query = _terms(question)
    ranked: list[SectionHit] = []
    for record in records_for_question(question, records):
        overlap = query & _terms(record.text)
        if overlap:
            score = len(overlap) / max(1, len(query))
            ranked.append(SectionHit(record.record_id, record.park_name, record.section, record.source_url, record.source_as_of, round(score, 6), record.text))
    ranked.sort(key=lambda hit: (-hit.score, hit.record_id))
    return ranked[:top_k]


def reciprocal_rank_fusion(*ranked_lists: list[SectionHit], top_k: int = 3, constant: int = 60) -> list[SectionHit]:
    """Combine independent rankings without pretending their score scales match."""
    fused: dict[str, tuple[float, SectionHit]] = {}
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked, start=1):
            previous = fused.get(hit.record_id)
            fused[hit.record_id] = ((previous[0] if previous else 0.0) + 1 / (constant + rank), hit)
    ordered = sorted(fused.values(), key=lambda item: (-item[0], item[1].record_id))
    return [SectionHit(hit.record_id, hit.park_name, hit.section, hit.source_url, hit.source_as_of, round(score, 6), hit.text) for score, hit in ordered[:top_k]]
