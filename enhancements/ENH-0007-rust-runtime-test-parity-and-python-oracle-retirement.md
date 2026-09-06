# ENH-0007 — Rust runtime test parity and Python oracle retirement

**Status:** Implemented; deployed request path remains Rust-only. The remaining Python modules are
support code; the historical runtime tests were subsequently removed by ENH-0011.

## Objective

Make the Rust test suite the sole authoritative test owner for the deployed request Lambda, then
retire the Python Lambda/capture wiring and its CI oracle gate without removing Python CDK,
evaluation, ingestion, or offline-support tooling that still has an active purpose.

This is a test-ownership and infrastructure-cleanup enhancement. It does not change the user-facing
SMS contract, provider behavior, RAG corpus, or deferred ingestion boundary.

## Scope

- Add Rust contract coverage for provider/model failure fallbacks and retrieval failure boundaries.
- Keep the Rust suite responsible for event parsing, delivery guards, routing, adapter call counts,
  grounding, context behavior, SMS bounds, fallback behavior, and capture/live side-effect guards.
- Remove the Python request Lambda and Python capture twin from the CDK graph.
- Reject the former `rust_runtime=false` rollback switch and `python_capture` context so a future
  synth cannot silently recreate a Python request path.
- Stop treating the historical Python request-runtime test group as an active validation boundary.
  Its final removal is tracked by ENH-0011.
- Retain Python CDK, evaluation, fire-ban ingestion, retrieval tooling, and support modules.
- Preserve the historical DynamoDB `MessageContext` resource in the template for a separate,
  explicitly reviewed infrastructure cleanup; the deployed Rust function uses the Rust context
  table.

## Deliberate non-goals

- Do not rewrite CDK in Rust.
- Do not delete Python modules that are still imported by evaluation or support tooling.
- Do not add live Bedrock/provider calls, ingestion, or real SMS sends to ordinary tests or CI.
- Do not claim fire-ban ingestion, RAG freshness, recurring refresh, or live ranking is complete.
- Do not treat Rust test parity as proof of live provider or deployed behavior without the separate
  capture/provider/deployment gates.

## Acceptance criteria

1. Rust tests cover the deployed request-path failure boundaries and continue to pass without AWS,
   network, or carrier side effects.
2. CDK synthesizes a Rust request Lambda only; no Python handler or Python capture Lambda appears in
   the synthesized graph.
3. The former Python rollback/capture contexts fail closed rather than recreating a request path.
4. CI runs the Rust contract gate and retained Python CDK/evaluation/support gate, but has no Python
   request-runtime oracle gate or Python rollback synth.
5. Python remains available only as explicitly classified CDK/evaluation/ingestion/offline support;
   deleting those modules is not implied by this enhancement.
6. `STATUS.md`, `docs/testing.md`, and the enhancement register describe the actual ownership and
   deferred work without calling retained Python reference tests deployed behavior.

## Verification plan

- Run the focused Rust contract tests, formatter, locked check, clippy, and Lambda package build.
- Run Ruff, mypy, the retained Python test gate, and offline evaluation gates.
- Synthesize the default stack and inspect the template for absence of Python request/capture
  Lambdas and presence of the Rust subscription/IAM boundary.
- Run the final repository validation gate after review and focused fixes.
- Deploy only if the normal target is not already at the same Rust-only runtime boundary; a deploy
  must use the existing explicit SSO/AWS workflow and must not include an SMS smoke test.

## Implementation record

- Rust failure-path contract tests were added to `rust/tests/runtime_contracts.rs`.
- Python request and capture Lambda definitions were removed from
  `infrastructure/sms_assistant_stack.py`.
- CI no longer runs the historical Python request-runtime marker or the Python rollback synth.
- Python support/evaluation modules remain intentionally retained and are not presented as live
  runtime code.
