# ENH-0013 — RAG corpus and tuning evidence pack

## Status

Implemented locally; Bedrock ingestion and Knowledge Base promotion remain deferred.

## Objective

Turn the existing RAG baseline into a demonstrable, reproducible tuning story: section-aware
corpus records, local semantic retrieval, hybrid comparison, deeper use-case coverage, and a
concise redacted report.

## Scope and non-goals

The implementation follows [`stage-9.3.4-rag-evidence-pack.md`](../specs/stage-9.3.4-rag-evidence-pack.md).
It does not change the deployed Rust request path or the Bedrock Knowledge Base configuration.

## Acceptance and capability tests

- `tests/test_rag_section_eval.py` covers section parsing, metadata, splitting, scoping, and
  deterministic hybrid ranking.
- `tests/test_retrieval.py` continues to cover the deployed retrieval adapter boundary.
- `scripts/rag_local_demo.py --mode lexical` demonstrates section-level evidence without AWS.
- `scripts/rag_local_demo.py --mode semantic` uses the optional local BGE model when installed.
- `scripts/rag_evidence_report.py` emits a redacted aggregate report without raw questions,
  excerpts, model responses, or provider payloads.

## Validation results

- Section parser, scoping, splitting, and routing tests: passed.
- Local semantic BGE demo: passed offline from the cached model.
- Local hybrid demo: passed offline from the cached model.
- Aggregate evidence: [`docs/rag-tuning-report.md`](../docs/rag-tuning-report.md).
- Ruff: passed.
- Mypy: passed.
- Full pytest: 83 passed, 19 skipped.
- Offline evaluation: 15 passed, 7 skipped.
- CDK synthesis: passed with existing deprecation/feature-flag warnings.
- `git diff --check`: passed.

## Deployment/live-verification status

No deployment or live check is required. The existing Bedrock/Titan configuration remains the
comparison baseline and is not re-ingested or promoted by this enhancement.

## Implementing commit

To be recorded after the change is committed.
