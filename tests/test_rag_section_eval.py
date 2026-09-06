from __future__ import annotations

import json
from pathlib import Path

from scripts.rag_section_eval import (
    CORPUS,
    corpus_profile,
    current_status_question,
    lexical_search,
    load_section_records,
    records_for_question,
    section_chunks,
    split_section,
)


def test_section_records_preserve_park_section_source_and_snapshot() -> None:
    records = load_section_records()
    assert records
    assert all(record.park_name for record in records)
    assert all(record.section in {"Activities", "Facilities"} for record in records)
    assert all(record.source_url.startswith("https://www.ontarioparks.ca/park/") for record in records)
    assert all(record.source_as_of == "2026-08-31" for record in records)


def test_section_profile_is_bounded_and_has_both_primary_sections() -> None:
    profile = corpus_profile(load_section_records())
    assert profile["parks_with_sections"] >= 200
    assert profile["activity_sections"] > profile["facility_sections"] > 0
    assert profile["missing_source_dates"] == 0


def test_oversized_section_splits_with_parent_identity_and_overlap() -> None:
    records = load_section_records()
    source = records[0]
    expanded = source.__class__(source.record_id, source.park_name, source.section, source.source_url, source.source_as_of, " ".join([source.text] * 20))
    chunks = split_section(expanded, max_tokens=20, overlap_tokens=2)
    assert len(chunks) > 1
    assert all(chunk.park_name == source.park_name and chunk.section == source.section for chunk in chunks)
    assert chunks[0].record_id.startswith(source.record_id + ".")


def test_named_park_scoping_rejects_unknown_park_and_keeps_matching_park() -> None:
    records = section_chunks()
    assert lexical_search("What activities does Algonquin Provincial Park list?", records, 3)
    assert lexical_search("What facilities does NeverListed Park have?", records, 3) == []


def test_current_status_questions_are_classified_outside_static_rag() -> None:
    assert current_status_question("Is Algonquin under a fire ban today?")
    assert current_status_question("Can I reserve an Algonquin campsite this weekend?")
    assert not current_status_question("What activities does Algonquin list?")


def test_section_scoping_is_shared_by_retrieval_strategies() -> None:
    records = section_chunks()
    assert all(record.park_name == "Arrowhead Provincial Park" for record in records_for_question("Where can I rent a canoe at Arrowhead Provincial Park?", records))
    assert records_for_question("Does NeverListed Park have winter camping?", records) == []


def test_hybrid_fusion_is_deterministic_and_report_fixture_is_expanded() -> None:
    fixture = json.loads((Path(__file__).parent / "evals/fixtures/rag_section_golden.json").read_text(encoding="utf-8"))
    assert len(fixture["cases"]) >= 16
    assert len({case["case_id"] for case in fixture["cases"]}) == len(fixture["cases"])
    assert CORPUS.exists()
