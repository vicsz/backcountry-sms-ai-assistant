"""Deterministic, offline Stage 9.3.3 retrieval evaluation.

This is a lexical baseline, not a simulation of Titan embeddings or Bedrock ranking.
It never makes network calls and report output intentionally omits raw questions/excerpts.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data/rag/ontario-provincial-parks-guide.md"
GOLDEN = ROOT / "tests/evals/fixtures/retrieval_golden.json"
TOP_K = (1, 3, 5)
VARIANTS = (("fixed-200-20", 200, 20), ("fixed-300-30", 300, 30), ("fixed-500-50", 500, 50), ("heading-aware", 500, 0))
THRESHOLDS = {"recall_at_3": 0.50, "precision_at_3": 0.25, "park_section_recall_at_3": 0.50, "unsupported_exclusion": 1.0, "current_status_routing": 1.0, "refusal_correctness": 1.0, "citation_accuracy": 0.50, "citation_completeness": 0.50, "groundedness": 1.0, "unsupported_claim_rate": 0.0, "max_p95_retrieval_ms": 100.0, "max_cost_per_question_usd": 0.0}
STOP = {"a", "an", "and", "are", "based", "does", "for", "have", "i", "in", "is", "list", "me", "of", "on", "the", "to", "what", "which", "where", "with"}


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    park: str
    section: str
    source_url: str
    text: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    score: float
    park: str
    section: str
    source_url: str
    evidence: tuple[str, ...]
    text_terms: tuple[str, ...]


def tokens(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", value.casefold()) if word not in STOP and len(word) > 2}


def corpus_sections() -> list[tuple[str, str, str, str]]:
    sections = []
    for block in re.split(r"(?=^##\s+)", CORPUS.read_text(encoding="utf-8"), flags=re.MULTILINE):
        heading = re.match(r"##\s+([^\n]+)", block)
        url = re.search(r"https://www\.ontarioparks\.ca/park/[A-Za-z0-9-]+", block)
        if heading and url:
            sections.append((heading.group(1).strip(), url.group(0), block.strip(), block))
    return sections


def _evidence(park: str, text: str) -> tuple[str, ...]:
    key = {"Algonquin Provincial Park": "algonquin", "Killarney Provincial Park": "killarney", "Arrowhead Provincial Park": "arrowhead"}.get(park)
    if not key:
        return ()
    lowered = text.casefold()
    values = []
    if "activities listed:" in lowered:
        values.append(f"{key}.activities")
    if "relevant facilities/rentals listed:" in lowered:
        values.append(f"{key}.facilities")
    return tuple(values)


def build_chunks(variant: str, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for park, url, text, _ in corpus_sections():
        windows = []
        if variant == "heading-aware":
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            heading = lines[0] if lines else ""
            current = [heading]
            for line in lines[1:]:
                candidate = current + [line]
                if len(candidate) > size and len(current) > 1:
                    windows.append(current)
                    current = [heading, line]
                else:
                    current = candidate
            if len(current) > 1:
                windows.append(current)
        else:
            words = text.split()
            step = max(1, size - overlap)
            windows = [words[start:start + size] for start in range(0, len(words), step)]
        for index, window in enumerate(windows):
            excerpt = " ".join(window) if isinstance(window, list) else window
            if not excerpt:
                continue
            chunks.append(Chunk(f"{variant}:{len(chunks):04d}:{index}", park, _section_for_text(excerpt), url, excerpt, _evidence(park, excerpt)))
    return chunks


def _section_for_text(text: str) -> str:
    lowered = text.casefold()
    if "facilities/rentals listed:" in lowered or "rentals -" in lowered:
        return "Facilities"
    if "activities listed:" in lowered:
        return "Activities"
    return "Guide"


def retrieve(question: str, chunks: list[Chunk], top_k: int) -> list[Hit]:
    query = tokens(question)
    ranked = []
    for chunk in chunks:
        overlap = query & tokens(chunk.text)
        if overlap:
            score = len(overlap) / max(1, len(query))
            ranked.append(Hit(chunk.chunk_id, round(score, 6), chunk.park, chunk.section, chunk.source_url, chunk.evidence, tuple(sorted(tokens(chunk.text)))) )
    return sorted(ranked, key=lambda hit: (-hit.score, hit.chunk_id))[:top_k]


def current_status(question: str) -> bool:
    return bool(re.search(r"\b(?:today|tomorrow|currently|open|available|availability|fire ban|closed|closure|operating|hours|prices?|reserv(?:e|ation|ations)?|campsites?)\b", question.casefold()))


def _citation_score(case: dict[str, Any], hits: list[Hit]) -> tuple[int, int]:
    required = case["required_citation"]
    required_park = required.get("park", "")
    required_sections = set(required.get("sections", []))
    citation_hits = [
        hit for hit in hits
        if (not required_park or required_park == "Ontario provincial parks" or hit.park == required_park)
        and (not required_sections or hit.section in required_sections)
    ]
    accuracy = int(bool(citation_hits)) if required_park or required_sections else int(not hits)
    completeness = int(all(any(hit.section == section for hit in citation_hits) for section in required_sections)) if required_sections else int(not hits)
    return accuracy, completeness


def _render_deterministic_answer(case: dict[str, Any], hits: list[Hit]) -> dict[str, Any]:
    """Render a local evidence-only answer shape; no language model is called."""
    if case["class"] == "current-status":
        return {"outcome": "redirect", "claims": (), "citations": ()}
    if case["class"] == "negative":
        return {"outcome": "refusal", "claims": (), "citations": ()}
    gold = set(case["gold_evidence"])
    found = {item for hit in hits for item in hit.evidence}
    if not gold <= found:
        return {"outcome": "refusal", "claims": (), "citations": ()}
    citations = tuple((hit.park, hit.section) for hit in hits if gold & set(hit.evidence))
    return {"outcome": "answer", "claims": tuple(case["acceptable_claims"]), "citations": citations}


def _case_score(case: dict[str, Any], hits: list[Hit]) -> dict[str, Any]:
    gold = set(case["gold_evidence"])
    found = {item for hit in hits for item in hit.evidence}
    relevant = [hit for hit in hits if gold & set(hit.evidence)]
    recall = len(found & gold) / len(gold) if gold else None
    precision = len(relevant) / len(hits) if hits else 1.0 if not gold else 0.0
    answer = _render_deterministic_answer(case, hits)
    citation_accuracy, citation_completeness = _citation_score(case, hits)
    claims = set(tokens(" ".join(answer["claims"])))
    grounded = not claims or claims <= {token for hit in hits for token in hit.text_terms}
    expected_outcome = {"supported": "answer", "negative": "refusal", "current-status": "redirect"}[case["class"]]
    return {
        "case_id": case["case_id"],
        "class": case["class"],
        "retrieved_ids": [hit.chunk_id for hit in hits],
        "scores": [hit.score for hit in hits],
        "evidence_ids": sorted(found),
        "recall": recall,
        "precision": round(precision, 6),
        "park_section_recall": bool(relevant),
        "citation_accuracy": citation_accuracy,
        "citation_completeness": citation_completeness,
        "groundedness": int(grounded),
        "unsupported_claim": 0 if grounded else 1,
        "refusal_correctness": int(answer["outcome"] == expected_outcome),
        "answer_mode": "deterministic-evidence-rubric",
    }


def _percentile(samples: list[float], fraction: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return round(ordered[index], 6)


def _timing_samples(case: dict[str, Any], chunks: list[Chunk], top_k: int) -> tuple[list[float], list[float]]:
    retrieval_ms: list[float] = []
    generation_ms: list[float] = []
    for _ in range(20):
        started = time.perf_counter()
        hits = retrieve(case["question"], chunks, top_k)
        retrieval_ms.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        _case_score(case, hits)
        generation_ms.append((time.perf_counter() - started) * 1000)
    return retrieval_ms, generation_ms


def evaluate(date: str = "2026-09-05") -> dict[str, Any]:
    corpus = CORPUS.read_bytes()
    fixture = json.loads(GOLDEN.read_text(encoding="utf-8"))
    all_cases = fixture["cases"]
    candidates = []
    for name, size, overlap in VARIANTS:
        chunks = build_chunks(name, size, overlap)
        for top_k in TOP_K:
            case_results = []
            routed = 0
            retrieval_timing: list[float] = []
            generation_timing: list[float] = []
            for case in all_cases:
                if case["class"] == "current-status":
                    is_routed = current_status(case["question"])
                    routed += int(is_routed)
                    case_results.append({"case_id": case["case_id"], "class": case["class"], "retriever_called": False, "routed_to": "live-status-boundary", "refusal_correctness": int(is_routed)})
                else:
                    hits = retrieve(case["question"], chunks, top_k)
                    case_results.append(_case_score(case, hits))
                    retrieval_samples, generation_samples = _timing_samples(case, chunks, top_k)
                    retrieval_timing.extend(retrieval_samples)
                    generation_timing.extend(generation_samples)
            retrieval_cases = [item for item in case_results if item.get("class") != "current-status"]
            supported = [item for item in retrieval_cases if item["class"] == "supported"]
            negative = [item for item in retrieval_cases if item["class"] == "negative"]
            all_evaluated = retrieval_cases + [item for item in case_results if item.get("class") == "current-status"]
            candidates.append({
                "variant": name,
                "top_k": top_k,
                "chunk_count": len(chunks),
                "current_status_routing": routed / sum(case["class"] == "current-status" for case in all_cases),
                "aggregate": {
                    "recall_at_k": round(sum(item["recall"] or 0 for item in supported) / len(supported), 6),
                    "precision_at_k": round(sum(item["precision"] for item in supported) / len(supported), 6),
                    "park_section_recall": round(sum(item["park_section_recall"] for item in supported) / len(supported), 6),
                    "unsupported_evidence_exclusion": round(sum(not item["retrieved_ids"] for item in negative) / len(negative), 6),
                    "current_status_routing": routed / sum(case["class"] == "current-status" for case in all_cases),
                    "refusal_correctness": round(sum(item["refusal_correctness"] for item in all_evaluated) / len(all_evaluated), 6),
                    "citation_accuracy": round(sum(item["citation_accuracy"] for item in supported) / len(supported), 6),
                    "citation_completeness": round(sum(item["citation_completeness"] for item in supported) / len(supported), 6),
                    "groundedness": round(sum(item["groundedness"] for item in supported) / len(supported), 6),
                    "unsupported_claim_rate": round(sum(item["unsupported_claim"] for item in supported) / len(supported), 6),
                    "p50_retrieval_ms": _percentile(retrieval_timing, 0.50),
                    "p95_retrieval_ms": _percentile(retrieval_timing, 0.95),
                    "p50_generation_rubric_ms": _percentile(generation_timing, 0.50),
                    "p95_generation_rubric_ms": _percentile(generation_timing, 0.95),
                },
                "cases": case_results,
            })
    return {
        "status": "implemented-offline-only",
        "objective": "Compare bounded local chunking and top-k retrieval variants without modeling Bedrock equivalence.",
        "date": date,
        "operator": "Backcountry Implementer",
        "decision": "retain-baseline-pending-live-validation",
        "baseline": {"chunking": "fixed-300-30", "embedding_model": "amazon.titan-embed-text-v2:0", "provider_calls": False},
        "corpus": {"sha256": hashlib.sha256(corpus).hexdigest(), "source": "checked-in Ontario Parks guide", "source_snapshot": "2026-08-31"},
        "fixture_version": fixture["fixture_version"],
        "retrieval": {"implementation": "deterministic lexical overlap; not Bedrock/Titan", "candidate_matrix": [{"variant": name, "size_tokens": size, "overlap_tokens": overlap} for name, size, overlap in VARIANTS], "top_k": list(TOP_K), "score_threshold": 0.0},
        "generation": {"mode": "deterministic evidence-only answer/refusal rubric; no language model answer generated", "model": None, "cost_usd_per_question": 0.0},
        "thresholds_preregistered": THRESHOLDS,
        "candidates": candidates,
        "limitations": ["Lexical ranking is a deterministic retrieval baseline, not a Bedrock embedding result.", "Generation metrics evaluate a deterministic evidence-only answer shape, not prose quality from an LLM.", "Cost is zero provider cost because this evaluator makes no network calls; Bedrock embedding, ingestion, retrieval, and generation cost remains unavailable.", "Current-status cases are routing checks only and never enter RAG."],
    }


def main() -> None:
    if "--demo" in sys.argv:
        result = evaluate()
        candidate = next(item for item in result["candidates"] if item["variant"] == "fixed-300-30" and item["top_k"] == 3)
        print(json.dumps({"query": "What facilities are listed for Arrowhead?", "candidate": "fixed-300-30", "top_k": 3, "retrieved": [case for case in candidate["cases"] if case["case_id"] == "arrowhead.facilities.001"]}, indent=2, sort_keys=True))
    else:
        print(json.dumps(evaluate(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
