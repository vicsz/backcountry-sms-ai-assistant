# ENH-0004 — RAG quality gates and park-scoped retrieval

## Status

Partially implemented — local quality gates and deterministic routing are complete; live Knowledge
Base metadata/refresh work remains deferred.

## Outcome

Named-park questions must not accept generic hits from another park. Questions about hours, prices,
operating details, openings, closures, reservations, or current availability must leave the
one-time static guide boundary. Stable guide questions may still use bounded RAG evidence.

## Implemented

- Python and Rust retrieval paths apply explicit park scoping and reject unknown named parks.
- Python and Rust route time-sensitive hours/prices/operating questions before retrieval.
- Python and Rust tests cover generic-hit rejection and the time-sensitive routing boundary.
- The deterministic local evaluator records fixed-size and heading-aware chunk candidates, top-k
  values, park/section evidence, negative questions, current-status routing, citations, grounding,
  latency, and cost boundaries.

## Measured local result

The fixed-300/30, top-k-3 candidate remains the recorded baseline. The local lexical evaluator
reports recall 0.666667, precision 0.5, park/section recall 0.666667, unsupported-evidence
exclusion 1.0, current-status routing 1.0, p95 retrieval about 7.2 ms, and zero provider cost.
The remaining citation completeness and groundedness misses are evidence that this evaluator is a
safe diagnostic baseline, not proof that Titan embeddings or Bedrock generation are optimized.
No candidate is promoted on this result alone.

## Deferred gates

- Re-ingest with per-park/per-section metadata and source-date fields.
- Validate the actual Bedrock embedding/vector-store ranking and generated answers.
- Establish freshness and source-date handling, recurring ingestion, and a separately authorized
  live retrieval report.
- Promote a new Knowledge Base configuration only after the preregistered retrieval, citation,
  grounding, latency, cost, and current-status gates pass.

## Non-goals

No source refresh, fire-ban ingestion, live SMS, production environment, or claim that the checked-
in corpus is current.

## Acceptance tests

- `tests/test_retrieval.py` and `tests/test_handler.py` pass.
- `rust/tests/runtime_contracts.rs` covers the same deployed request-path boundaries.
- `scripts/retrieval_eval.py` runs offline without AWS and emits redacted aggregate evidence.
- A deployed live baseline remains unchanged until a later explicit promotion gate.
