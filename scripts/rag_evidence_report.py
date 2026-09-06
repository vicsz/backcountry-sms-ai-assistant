"""Emit a redacted corpus and local retrieval evidence report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from rag_local_demo import LocalSemanticIndex, _hybrid_search_with_index
from rag_section_eval import (
    CORPUS,
    corpus_profile,
    current_status_question,
    lexical_search,
    section_chunks,
)

GOLDEN = Path(__file__).resolve().parents[1] / "tests/evals/fixtures/rag_section_golden.json"


def _evaluate_mode(cases: list[dict[str, Any]], records: list, mode: str, index: LocalSemanticIndex | None = None) -> dict[str, Any]:
    results = []
    for case in cases:
        question = str(case["question"])
        routed = current_status_question(question)
        if routed:
            hits = []
        elif mode == "lexical":
            hits = lexical_search(question, records, 3)
        elif mode == "semantic" and index is not None:
            hits = index.search(question, 3)
        elif mode == "hybrid" and index is not None:
            hits = _hybrid_search_with_index(question, records, index, 3)
        else:
            raise ValueError(f"unsupported evaluation mode: {mode}")
        hit_ids = {hit.record_id for hit in hits}
        gold = set(case["gold_records"])
        results.append({
            "case_id": case["case_id"],
            "class": case["class"],
            "retriever_called": not routed,
            "retrieved_records": [hit.record_id for hit in hits],
            "gold_records_found": sorted(hit_ids & gold),
            "recall": round(len(hit_ids & gold) / len(gold), 6) if gold else None,
            "precision": round(len(hit_ids & gold) / len(hit_ids), 6) if hit_ids else (1.0 if not gold else 0.0),
            "correct_boundary": bool(routed and case["class"] == "current-status") if case["class"] == "current-status" else (bool(not hit_ids) if case["class"] == "negative" else bool(hit_ids & gold)),
        })
    supported = [item for item in results if item["class"] == "supported"]
    boundary = [item for item in results if item["class"] in {"negative", "current-status"}]
    return {
        "aggregate": {
            "supported_recall": round(sum(item["recall"] or 0 for item in supported) / len(supported), 6),
            "supported_precision": round(sum(item["precision"] for item in supported) / len(supported), 6),
            "boundary_correctness": round(sum(item["correct_boundary"] for item in boundary) / len(boundary), 6),
        },
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-semantic", action="store_true")
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    args = parser.parse_args()
    records = section_chunks()
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
    evaluations: dict[str, Any] = {"lexical": _evaluate_mode(cases, records, "lexical")}
    if args.with_semantic:
        index = LocalSemanticIndex(records, args.model)
        evaluations["semantic"] = _evaluate_mode(cases, records, "semantic", index)
        evaluations["hybrid"] = _evaluate_mode(cases, records, "hybrid", index)
    report = {
        "status": "implemented-offline-only",
        "decision": "retain-section-first-local-baseline; no-bedrock-promotion",
        "corpus": {"sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(), **corpus_profile(records)},
        "chunking": {"strategy": "section-first", "max_tokens": 300, "overlap_tokens": 0},
        "local_semantic_model": args.model,
        "golden_case_count": len(cases),
        "evaluations": evaluations,
        "limitations": [
            "The lexical report is not Bedrock/Titan evidence.",
            "The local semantic model is a demonstration baseline and does not change the deployed Knowledge Base.",
            "Snapshot facts are not current operational facts.",
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
