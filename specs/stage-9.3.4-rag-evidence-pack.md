# Stage 9.3.4 — RAG corpus and tuning evidence pack

**Status:** Implemented locally; no Bedrock Knowledge Base promotion or ingestion automation.

## Objective

Demonstrate, with reproducible local evidence, how Ontario Parks RAG chunking and retrieval choices
were evaluated. The section-first design must preserve park and section identity, support bounded
semantic and hybrid retrieval, and make unsupported/current-status behavior measurable.

## Scope

- Derive machine-readable park/section records from the checked-in Ontario Parks snapshot.
- Treat each park section as the primary chunk boundary; split oversized sections deterministically
  while repeating the park and section metadata.
- Compare the existing lexical baseline with a local BGE-small semantic retriever and a bounded
  reciprocal-rank hybrid.
- Expand the reviewed golden cases across direct lookups, paraphrases, multi-park questions,
  rental/facility distinctions, unknown parks, unsupported facts, and current-status boundaries.
- Produce a redacted report describing corpus coverage, candidates, metrics, failures, and the
  retained recommendation.

## Explicit non-goals

- No automated ingestion, scheduled refresh, source polling, or content re-download.
- No Bedrock Knowledge Base re-ingestion, embedding-model change, vector-store change, deployment,
  or live SMS.
- No current hours, prices, closures, reservations, availability, fire-ban status, or weather
  claim is made current by this work.
- No local language model answer generator is required; evidence display and deterministic answer
  refusal are sufficient for the local demonstration.

## Decisions to test

1. Section-first chunks: `park × section`, with bounded subchunks only for oversized sections.
2. Zero overlap across independent sections; bounded overlap only within a split section.
3. BGE-small-en-v1.5 as the local semantic demonstration model.
4. Existing lexical retrieval as the transparent control.
5. Reciprocal-rank fusion as the first hybrid strategy; no reranker or fine-tuning.
6. Titan Text Embeddings V2 remains the Bedrock-relevant baseline and is evaluated separately.

## Acceptance criteria

- Section records include stable IDs, park, section, official URL, snapshot date, and source text.
- Corpus profiling reports record counts, section coverage, and missing metadata without exposing
  account-specific or provider payload data.
- Local lexical, semantic, and hybrid retrieval run without AWS calls; semantic mode fails with a
  clear installation instruction when the optional local dependency is absent.
- Golden cases cover supported, paraphrased, multi-park, unsupported, unknown-park, and
  current-status questions, with retrieval and routing scored separately.
- The report records recall, precision, park/section recall, wrong-park leakage, refusal/current
  routing, citation completeness, latency, and model/chunking settings.
- No candidate is described as Bedrock/Titan evidence, and no candidate is promoted or deployed.
- Ruff, mypy, full pytest, the offline evaluator, and CDK synthesis pass.

## Evidence

The aggregate results are recorded in [`docs/rag-tuning-report.md`](../docs/rag-tuning-report.md).
