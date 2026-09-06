"""Demonstrate section-first local retrieval without AWS."""

from __future__ import annotations

import argparse
import json
from typing import Any

from rag_section_eval import (
    SectionHit,
    SectionRecord,
    current_status_question,
    lexical_search,
    reciprocal_rank_fusion,
    records_for_question,
    section_chunks,
)


class LocalSemanticIndex:
    def __init__(self, records: list[SectionRecord], model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise SystemExit("Semantic mode requires optional RAG dependencies: pip install -r requirements-rag-dev.txt") from error
        self.records = records
        self.model = SentenceTransformer(model_name)
        self.vectors = self.model.encode([record.text for record in records], normalize_embeddings=True, show_progress_bar=False)

    def search(self, question: str, top_k: int) -> list[SectionHit]:
        query = self.model.encode([question], normalize_embeddings=True, show_progress_bar=False)[0]
        allowed = {record.record_id for record in records_for_question(question, self.records)}
        scored = []
        for record, vector in zip(self.records, self.vectors, strict=True):
            if record.record_id not in allowed:
                continue
            scored.append((float(vector @ query), record))
        scored.sort(key=lambda item: (-item[0], item[1].record_id))
        return [SectionHit(record.record_id, record.park_name, record.section, record.source_url, record.source_as_of, round(score, 6), record.text) for score, record in scored[:top_k]]


def _semantic_search(question: str, records: list[SectionRecord], model_name: str, top_k: int) -> list[SectionHit]:
    return LocalSemanticIndex(records, model_name).search(question, top_k)


def _hybrid_search_with_index(question: str, records: list[SectionRecord], index: LocalSemanticIndex, top_k: int) -> list[SectionHit]:
    lexical = lexical_search(question, records, max(top_k, 10))
    semantic = index.search(question, max(top_k, 10))
    return reciprocal_rank_fusion(lexical, semantic, top_k=top_k)


def _hybrid_search(question: str, records: list[SectionRecord], model_name: str, top_k: int) -> list[SectionHit]:
    return _hybrid_search_with_index(question, records, LocalSemanticIndex(records, model_name), top_k)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--mode", choices=("lexical", "semantic", "hybrid"), default="lexical")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    records = section_chunks()
    routed_to = None
    if current_status_question(args.question):
        hits = []
        routed_to = "live-status-boundary"
    elif args.mode == "lexical":
        hits = lexical_search(args.question, records, args.top_k)
    elif args.mode == "semantic":
        hits = _semantic_search(args.question, records, args.model, args.top_k)
    else:
        hits = _hybrid_search(args.question, records, args.model, args.top_k)
    payload: dict[str, Any] = {
        "mode": args.mode,
        "model": args.model if args.mode != "lexical" else None,
        "question": args.question,
        "routed_to": routed_to,
        "chunking": "section-first; max_tokens=300; overlap_tokens=0",
        "hits": [
            {"record_id": hit.record_id, "park": hit.park_name, "section": hit.section, "source_url": hit.source_url, "source_as_of": hit.source_as_of, "score": hit.score, "text": hit.text}
            for hit in hits
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
