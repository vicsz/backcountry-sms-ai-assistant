from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from botocore.exceptions import ReadTimeoutError

from backcountry_sms.retrieval import (
    MAX_RETRIEVAL_RESULTS,
    BedrockKnowledgeBaseRetriever,
    LocalRetriever,
    RetrievalCitation,
    RetrievalFailure,
    RetrievalResult,
)
from scripts.retrieval_eval import (
    GOLDEN,
    VARIANTS,
    build_chunks,
    current_status,
    evaluate,
    retrieve,
)

pytestmark = pytest.mark.legacy_python_runtime


def result(park: str = "Arrowhead", excerpt: str = "Arrowhead lists canoe rentals and a boat launch.", score: float = 0.9) -> RetrievalResult:
    return RetrievalResult(excerpt, RetrievalCitation(park, "Facilities", "https://www.ontarioparks.ca/park/arrowhead"), score)


def test_local_retriever_is_typed_bounded_test_double() -> None:
    retriever = LocalRetriever([result() for _ in range(MAX_RETRIEVAL_RESULTS + 1)])
    assert len(retriever.retrieve("What facilities are listed?")) == MAX_RETRIEVAL_RESULTS
    assert retriever.questions == ["What facilities are listed?"]


def test_corpus_sidecar_supplies_checked_in_source_metadata() -> None:
    sidecar = Path("data/rag/ontario-provincial-parks-guide.md.metadata.json")
    metadata = json.loads(sidecar.read_text())
    assert metadata["metadataAttributes"] == {
        "source_label": "Ontario Parks guide",
        "source_url": "https://www.ontarioparks.ca/park-locator",
        "corpus_snapshot": "2026-08-31",
        "corpus_sha256": "19273cf0e1711aeb40b049df45ecbad49c2e01f24733e565a5614c0befb83e74",
        "region": "ca-central-1",
        "embedding_model": "amazon.titan-embed-text-v2:0",
        "chunking": "fixed-size:300-tokens:30-token-overlap",
    }


def test_bedrock_retriever_caps_and_sanitizes_metadata() -> None:
    class Client:
        def retrieve(self, **kwargs: object) -> dict:
            assert kwargs["retrievalConfiguration"] == {"vectorSearchConfiguration": {"numberOfResults": 3}}
            return {"retrievalResults": [
                {"content": {"text": "  Arrowhead has  canoe rentals.  "}, "score": 0.9,
                 "metadata": {"park_name": "Arrowhead", "section": "Facilities", "ignored": "secret"},
                 "location": {"s3Location": {"uri": "s3://private/corpus"}}},
                {"content": {"text": "too weak"}, "score": 0.1},
            ]}

    results = BedrockKnowledgeBaseRetriever("kb-123", Client()).retrieve("Arrowhead facilities")
    assert results == [RetrievalResult("Arrowhead has canoe rentals.", RetrievalCitation("Arrowhead", "Facilities", ""), 0.9, (("canoe_rentals", "yes"),))]


def test_bedrock_retriever_maps_timeout_without_payload_logging() -> None:
    class Client:
        def retrieve(self, **_kwargs: object) -> dict:
            raise ReadTimeoutError(endpoint_url="https://bedrock")

    try:
        BedrockKnowledgeBaseRetriever("kb-123", Client()).retrieve("question")
    except RetrievalFailure as error:
        assert error.category == "timeout"
    else:
        raise AssertionError("expected a retrieval failure")


def test_bedrock_retriever_preserves_live_shaped_source_and_custom_metadata() -> None:
    class Client:
        def retrieve(self, **_kwargs: object) -> dict:
            return {"retrievalResults": [{
                "content": {"text": "Arrowhead lists canoe rentals."},
                "score": 0.91,
                "metadata": {
                    "x-amz-bedrock-kb-source-uri": "s3://private/guide/ontario-provincial-parks-guide.md",
                    "source_url": "https://www.ontarioparks.ca/park/arrowhead",
                    "source_label": "Ontario Parks guide",
                    "park_name": "Arrowhead",
                    "section": "Facilities",
                    "claim_key": "canoe_rentals",
                    "claim_value": "yes",
                    "x-amz-bedrock-kb-data-source-id": "ignored-id",
                },
                "location": {"s3Location": {"uri": "s3://ignored/fallback"}},
            }]}

    results = BedrockKnowledgeBaseRetriever("kb-123", Client()).retrieve("Arrowhead canoe rentals")
    assert results == [RetrievalResult(
        "Arrowhead lists canoe rentals.",
        RetrievalCitation("Arrowhead", "Facilities", "https://www.ontarioparks.ca/park/arrowhead"),
        0.91,
        (("canoe_rentals", "yes"),),
    )]


def test_bedrock_retriever_reads_sidecar_attributes_and_excerpt_citation() -> None:
    class Client:
        def retrieve(self, **_kwargs: object) -> dict:
            return {"retrievalResults": [{
                "content": {"text": "## Arrowhead Provincial Park\n- Official page: https://www.ontarioparks.ca/park/arrowhead\n- Relevant facilities/rentals listed: Boat Launch(es); Rentals - Canoe."},
                "score": 0.9,
                "metadata": {
                    "metadataAttributes": {"source_label": "Ontario Parks guide"},
                    "x-amz-bedrock-kb-source-uri": "s3://private/guide/ontario-provincial-parks-guide.md",
                },
                "location": {"s3Location": {"uri": "s3://private/guide/ontario-provincial-parks-guide.md"}},
            }]}

    result = BedrockKnowledgeBaseRetriever("kb-123", Client()).retrieve("Arrowhead facilities")[0]
    assert result.citation == RetrievalCitation("Arrowhead Provincial Park", "Facilities", "https://www.ontarioparks.ca/park/arrowhead")


def test_bedrock_retriever_derives_park_from_mid_line_chunk_heading() -> None:
    class Client:
        def retrieve(self, **_kwargs: object) -> dict:
            return {"retrievalResults": [{
                "content": {"text": "captured 2026-08-31. ## Algonquin Provincial Park - Official page: https://www.ontarioparks.ca/park/algonquin - Activities listed: Canoeing."},
                "score": 0.95,
                "metadata": {"source_url": "https://www.ontarioparks.ca/park-locator"},
            }]}

    result = BedrockKnowledgeBaseRetriever("kb-123", Client()).retrieve("Algonquin activities")[0]

    assert result.citation.park_name == "Algonquin Provincial Park"
    assert result.citation.source_url == "https://www.ontarioparks.ca/park/algonquin"


def test_stage_9_3_3_fixture_covers_required_boundaries() -> None:
    cases = json.loads(GOLDEN.read_text())["cases"]
    questions = " ".join(case["question"] for case in cases).casefold()
    assert all(term in questions for term in ("algonquin", "killarney", "arrowhead", "canoe", "portage store", "neverlisted", "fire ban"))
    assert {case["class"] for case in cases} == {"supported", "negative", "current-status"}


def test_offline_retrieval_distinguishes_rentals_from_boat_launch() -> None:
    chunks = build_chunks("heading-aware", 500, 0)
    rentals = retrieve("Where can I rent a canoe at Arrowhead?", chunks, 5)
    arrowhead = [hit for hit in rentals if hit.park == "Arrowhead Provincial Park"]
    assert arrowhead and "arrowhead.facilities" in arrowhead[0].evidence
    assert {"rentals", "canoe"} <= set(arrowhead[0].text_terms)


def test_offline_current_status_boundary_never_retrieves() -> None:
    assert current_status("Is Algonquin under a fire ban today?")
    report = evaluate()
    current = next(item for item in report["candidates"] if item["variant"] == "fixed-300-30" and item["top_k"] == 3)
    assert current["current_status_routing"] == 1.0
    assert all(item.get("retriever_called") is False for item in current["cases"] if item["class"] == "current-status")


def test_offline_report_is_redacted_and_reproducible() -> None:
    report = evaluate()
    encoded = json.dumps(report, sort_keys=True)
    assert "What should I know" not in encoded
    assert "raw" not in encoded.casefold()
    assert len(report["candidates"]) == len(VARIANTS) * 3
    assert report["thresholds_preregistered"]["unsupported_claim_rate"] == 0.0


def test_local_demo_is_available_without_network() -> None:
    completed = subprocess.run([sys.executable, "scripts/benchmark_rag_retrieval.py", "--demo"], check=True, capture_output=True, text=True)
    assert '"query"' in completed.stdout
    assert "arrowhead.facilities" in completed.stdout
