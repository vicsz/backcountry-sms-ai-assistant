"""Bounded, redacted retrieval for the Ontario Parks guide knowledge base."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from .telemetry import emit_event
from .tracing import trace_span

MAX_RETRIEVAL_RESULTS = 3
MAX_EXCERPT_CHARS = 520
MAX_METADATA_CHARS = 120
MIN_RETRIEVAL_SCORE = 0.4
RAG_RETRIEVAL_CONNECT_TIMEOUT_SECONDS = 1
RAG_RETRIEVAL_READ_TIMEOUT_SECONDS = 4
RAG_RETRIEVAL_MAX_ATTEMPTS = 1
_GENERIC_PARK_TERMS = {"ontario", "provincial", "park", "parks"}


class RetrievalFailure(RuntimeError):
    """A safe, category-only retrieval failure."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class RetrievalCitation:
    park_name: str
    section: str
    source_url: str
    source_label: str = "Ontario Parks guide"

    @property
    def label(self) -> str:
        return f"Ontario Parks - {self.park_name}" if self.park_name else self.source_label


@dataclass(frozen=True)
class RetrievalResult:
    excerpt: str
    citation: RetrievalCitation
    score: float
    claims: tuple[tuple[str, str], ...] = ()


class Retriever(Protocol):
    def retrieve(self, question: str) -> list[RetrievalResult]: ...


class LocalRetriever:
    """Typed local test double; callers supply already-redacted fixture results."""

    def __init__(self, results: list[RetrievalResult] | None = None, error: RetrievalFailure | None = None) -> None:
        self.results = results or []
        self.error = error
        self.questions: list[str] = []

    def retrieve(self, question: str) -> list[RetrievalResult]:
        self.questions.append(question)
        if self.error is not None:
            raise self.error
        return _bounded_results([_enrich_result(item) for item in self.results])


class BedrockKnowledgeBaseRetriever:
    """Adapter for one Bedrock Retrieve call; it never logs source payloads."""

    def __init__(self, knowledge_base_id: str, client: Any | None = None) -> None:
        self.knowledge_base_id = knowledge_base_id
        self.client = client

    def retrieve(self, question: str) -> list[RetrievalResult]:
        if not self.knowledge_base_id:
            raise RetrievalFailure("unconfigured")
        started = time.perf_counter()
        try:
            with trace_span("bedrock.retrieve", provider="bedrock"):
                response = (self.client or _retrieval_client()).retrieve(
                    knowledgeBaseId=self.knowledge_base_id,
                    retrievalQuery={"text": question[:MAX_EXCERPT_CHARS]},
                    retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": MAX_RETRIEVAL_RESULTS}},
                )
        except (ConnectTimeoutError, ReadTimeoutError):
            _emit_retrieval_failure("timeout", started)
            raise RetrievalFailure("timeout") from None
        except EndpointConnectionError:
            _emit_retrieval_failure("unavailable", started)
            raise RetrievalFailure("unavailable") from None
        except Exception:  # noqa: BLE001 - map all provider errors to a safe category
            _emit_retrieval_failure("failed", started)
            raise RetrievalFailure("failed") from None
        results = response.get("retrievalResults") if isinstance(response, dict) else None
        if not isinstance(results, list):
            _emit_retrieval_failure("malformed", started)
            raise RetrievalFailure("malformed")
        parsed: list[RetrievalResult] = []
        for item in results:
            result = _parse_result(item)
            if result is not None:
                parsed.append(result)
        bounded = _bounded_results(parsed)
        duration_ms = (time.perf_counter() - started) * 1000
        emit_event("rag_retrieve", "success", provider="bedrock", duration_ms=duration_ms,
                   metrics={"RetrievalCalls": 1, "RetrievalDurationMs": duration_ms})
        return bounded


def configured_retriever() -> Retriever:
    return BedrockKnowledgeBaseRetriever(os.environ.get("RAG_KNOWLEDGE_BASE_ID", ""))


@lru_cache(maxsize=1)
def _retrieval_client() -> Any:
    return boto3.client(
        "bedrock-agent-runtime",
        config=Config(
            connect_timeout=RAG_RETRIEVAL_CONNECT_TIMEOUT_SECONDS,
            read_timeout=RAG_RETRIEVAL_READ_TIMEOUT_SECONDS,
            retries={"mode": "standard", "max_attempts": RAG_RETRIEVAL_MAX_ATTEMPTS},
        ),
    )


def _parse_result(item: object) -> RetrievalResult | None:
    if not isinstance(item, dict):
        return None
    content = item.get("content")
    score = item.get("score")
    if not isinstance(content, dict) or not isinstance(content.get("text"), str) or isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    excerpt = _safe_text(content["text"], MAX_EXCERPT_CHARS)
    if not excerpt or score < MIN_RETRIEVAL_SCORE:
        return None
    metadata_object = item.get("metadata")
    metadata = _metadata_attributes(metadata_object)
    excerpt_park, excerpt_section, excerpt_url = _derive_citation(excerpt)
    citation = RetrievalCitation(
        park_name=_safe_text(metadata.get("park_name") or metadata.get("park") or excerpt_park, MAX_METADATA_CHARS),
        section=_safe_text(metadata.get("section") or excerpt_section, MAX_METADATA_CHARS),
        source_url=_official_url(metadata.get("source_url") or metadata.get("official_url")) or excerpt_url,
        source_label=_safe_text(metadata.get("source_label") or "Ontario Parks guide", MAX_METADATA_CHARS),
    )
    claims = tuple(dict.fromkeys(_claims_from_metadata(metadata) + _claims_from_excerpt(excerpt)))
    return RetrievalResult(excerpt=excerpt, citation=citation, score=float(score), claims=claims)


def _bounded_results(results: list[RetrievalResult]) -> list[RetrievalResult]:
    useful = [item for item in results if item.excerpt and item.score >= MIN_RETRIEVAL_SCORE]
    return useful[:MAX_RETRIEVAL_RESULTS]


def filter_results_for_question(question: str, results: list[RetrievalResult]) -> list[RetrievalResult]:
    """Keep evidence scoped to an explicitly named park when one is identifiable."""
    question_terms = _park_terms(question)
    matching_terms = {
        term
        for result in results
        for term in _park_terms(result.citation.park_name)
        if term in question_terms
    }
    if matching_terms:
        return [
            result
            for result in results
            if _park_terms(result.citation.park_name) & matching_terms
        ]
    if _explicit_unknown_park(question):
        return []
    return results


def _park_terms(value: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9]+", value.casefold())
        if len(term) > 2 and term not in _GENERIC_PARK_TERMS
    }


def _explicit_unknown_park(question: str) -> bool:
    return bool(re.search(r"\b(?:[A-Z][A-Za-z0-9'/-]*\s+){1,4}Park\b", question))


def _metadata_attributes(value: object) -> dict[object, object]:
    """Read both Bedrock system metadata and the S3 sidecar's metadataAttributes."""
    if not isinstance(value, dict):
        return {}
    nested = value.get("metadataAttributes")
    attributes = nested if isinstance(nested, dict) else {}
    return {**attributes, **value}


def _official_url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    match = re.search(r"https://www\.ontarioparks\.ca/park/[A-Za-z0-9-]+", value)
    return match.group(0)[:MAX_METADATA_CHARS] if match else ""


def _derive_citation(excerpt: str) -> tuple[str, str, str]:
    """Recover citation context when a chunk has only Bedrock's source URI."""
    park = ""
    # Bedrock chunks can begin mid-line after the previous chunk's overlap.
    heading = re.search(r"(?:^|\s)##\s+([^\n]+)", excerpt)
    if heading:
        park = re.split(r"\s+-\s+Official page:", heading.group(1), maxsplit=1, flags=re.IGNORECASE)[0].strip()
    url_match = re.search(r"https://www\.ontarioparks\.ca/park/[A-Za-z0-9-]+", excerpt)
    corpus_url = ""
    if not (park and url_match):
        corpus_match = _corpus_citation(excerpt)
        park = park or corpus_match[0]
        corpus_url = corpus_match[1]
    section = ""
    if re.search(r"(?i)\b(?:facilit(?:y|ies)|rentals?|boat launch|comfort station|campsites?)\b", excerpt):
        section = "Facilities"
    elif re.search(r"(?i)\b(?:activities|canoeing|hiking|camping|boating|fishing)\b", excerpt):
        section = "Activities"
    return park, section, url_match.group(0) if url_match else corpus_url


@lru_cache(maxsize=1)
def _corpus_sections() -> tuple[tuple[str, str, str], ...]:
    path = Path(__file__).parents[1] / "data" / "rag" / "ontario-provincial-parks-guide.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    sections: list[tuple[str, str, str]] = []
    for block in re.split(r"(?=^##\s+)", text, flags=re.MULTILINE):
        heading = re.match(r"##\s+([^\n]+)", block)
        url = re.search(r"https://www\.ontarioparks\.ca/park/[A-Za-z0-9-]+", block)
        if heading and url:
            sections.append((heading.group(1).strip(), url.group(0), re.sub(r"\s+", " ", block).casefold()))
    return tuple(sections)


def _corpus_citation(excerpt: str) -> tuple[str, str]:
    needle = re.sub(r"\s+", " ", excerpt).strip().casefold()[:120]
    if not needle:
        return "", ""
    for park, url, normalized_section in _corpus_sections():
        if needle in normalized_section:
            return park, url
    return "", ""


def _safe_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _enrich_result(result: RetrievalResult) -> RetrievalResult:
    park, section, url = _derive_citation(result.excerpt)
    citation = RetrievalCitation(
        park_name=result.citation.park_name or park,
        section=result.citation.section or section,
        source_url=result.citation.source_url if _official_url(result.citation.source_url) else url,
        source_label=result.citation.source_label,
    )
    return RetrievalResult(result.excerpt, citation, result.score, result.claims or _claims_from_excerpt(result.excerpt))


def _claims_from_metadata(metadata: dict[object, object]) -> tuple[tuple[str, str], ...]:
    """Accept only simple, sidecar-safe claim metadata for conflict detection."""
    key = _safe_text(metadata.get("claim_key") or "", MAX_METADATA_CHARS).casefold()
    value = _safe_text(metadata.get("claim_value") or "", MAX_METADATA_CHARS).casefold()
    return ((key, value),) if key and value else ()


def _claims_from_excerpt(excerpt: str) -> tuple[tuple[str, str], ...]:
    """Extract only a small allowlist of explicit stable capability claims."""
    subjects = {
        "backcountry_camping": r"backcountry camping",
        "winter_camping": r"winter camping",
        "car_camping": r"car camping",
        "walk_in_camping": r"walk[- ]in camping",
        "canoe_rentals": r"canoe rentals?",
        "boat_launch": r"boat launch(?:es)?",
        "canoeing": r"canoeing",
    }
    claims: list[tuple[str, str]] = []
    lowered = excerpt.casefold()
    for key, pattern in subjects.items():
        for match in re.finditer(pattern, lowered):
            before = lowered[max(0, match.start() - 36):match.start()]
            value = "no" if re.search(r"\b(?:not|no|without|doesn't|does not)\b", before) else "yes"
            claims.append((key, value))
    return tuple(claims)


def _emit_retrieval_failure(category: str, started: float) -> None:
    duration_ms = (time.perf_counter() - started) * 1000
    emit_event("rag_retrieve", "failure", provider="bedrock", outcome=category, duration_ms=duration_ms,
               metrics={"RetrievalCalls": 1, "RetrievalFailures": 1, "RetrievalDurationMs": duration_ms})
