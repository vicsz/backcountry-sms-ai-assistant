# RAG tuning evidence report

Date: 2026-09-06
Status: Local evidence only; no Bedrock Knowledge Base promotion.

## Decision summary

The section-first representation is retained as the local experiment baseline. A simple hybrid of
lexical retrieval and `BAAI/bge-small-en-v1.5` produced the best result on the expanded local
fixture, but the result is not a Bedrock/Titan measurement and is not sufficient to change the
deployed Knowledge Base.

The current safe recommendation is:

- keep the deployed Titan Knowledge Base unchanged;
- use park/section records with bounded subchunks for local experiments;
- use the hybrid local demo to explain retrieval behavior;
- separately authorize any Titan re-ingestion and live comparison later.

## Corpus profile

| Measure | Result |
| --- | ---: |
| Snapshot park records | 341 |
| Parks with activity/facility sections | 277 |
| Parks without those primary sections | 64 |
| Activity sections | 276 |
| Facility sections | 153 |
| Section records | 429 |
| Missing section source dates | 0 |
| Corpus SHA-256 | `19273cf0e1711aeb40b049df45ecbad49c2e01f24733e565a5614c0befb83e74` |

The missing-primary-section count is a corpus coverage finding, not an automatic data defect:
some parks have only a locator page and no activity/facility labels in the checked-in snapshot.
It should be addressed through a separately reviewed content-expansion pass, not by inventing
facts in the evaluator.

## Experiment configuration

- Chunking: section-first; one `park × section` record, maximum 300 tokens, zero cross-section
  overlap.
- Oversized sections: deterministic bounded subchunks repeat the parent park and section identity.
- Fixture: 16 reviewed cases across direct lookup, paraphrase, multi-park, rental/facility,
  unknown-park, unsupported, and current-status questions.
- Top-k: 3.
- Semantic model: `BAAI/bge-small-en-v1.5`, local-only, 384-dimensional embeddings.
- Hybrid: reciprocal-rank fusion of lexical and local semantic rankings.
- Current-status questions: routed outside static RAG before retrieval.

## Results

| Strategy | Supported recall | Supported precision | Boundary correctness |
| --- | ---: | ---: | ---: |
| Lexical section-first | 0.864 | 0.424 | 1.000 |
| BGE semantic section-first | 0.864 | 0.409 | 1.000 |
| Lexical + BGE hybrid | **0.909** | 0.439 | 1.000 |

These results are directional. The local fixture is still small, and the precision values show
that returning more semantically related sections can introduce extra evidence. The report does
not claim that BGE ranking equals Titan ranking, or that local latency/cost predicts Bedrock.

## Demonstration commands

```text
.venv/bin/python scripts/rag_local_demo.py --mode lexical --question "Where can I rent a canoe at Arrowhead?"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/rag_local_demo.py --mode semantic --question "Where can I rent a canoe at Arrowhead?"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/rag_local_demo.py --mode hybrid --question "Where can I rent a canoe at Arrowhead?"
.venv/bin/python scripts/rag_evidence_report.py --with-semantic
```

The demo prints park, section, source date, score, and evidence text. The report omits raw
questions and excerpts and is suitable for committed aggregate evidence.

## Findings and next decision

1. Section-first chunks are a better explainability boundary than arbitrary token windows for the
   current park/facility corpus.
2. Hybrid retrieval improves local supported recall over the lexical control, but its precision
   remains modest and needs more reviewed cases before any threshold is treated as final.
3. Current-status routing and unknown-park scoping must remain deterministic controls; embeddings
   must not decide whether a static snapshot is current.
4. The next useful content work is a reviewed expansion of the 64 parks without primary sections,
   with per-section provenance. This is still a static snapshot task, not ingestion automation.
5. A later live experiment may compare the unchanged Titan V2 Knowledge Base against this section
   representation, but it requires a separate ingestion and live-retrieval authorization.
