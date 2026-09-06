# ENH-0006 — Python runtime boundary cleanup

## Status

Complete for the original cutover boundary. The rollback/oracle wiring described here was
subsequently retired by ENH-0007; this record remains the historical decision that established the
Rust-only deployed target.

## Decision

Rust owns the deployed request path. Python remains only where it is still needed for CDK,
fire-ban/RAG offline tooling, evaluation, and support. The Python Lambda and capture twin are no
longer represented in CDK or subscribed to inbound SNS.

## Cleanup completed

- Test ownership is documented in [`docs/testing.md`](../docs/testing.md).
- The default CDK path and CI gates are Rust-first; the former Python rollback/capture contexts now
  fail closed.
- RAG and fire-ban support modules are kept because their local/offline capabilities are still
  active and their dependencies have not been separately retired.

## Remaining safe cleanup

Review retained Python request helpers and historical oracle tests separately before deleting them;
selected evaluation/support tests still import shared helpers. Do not remove Python CDK, ingestion,
or evaluation code as part of this cleanup.

## Acceptance

- Default Demo synthesis contains Rust only for the request Lambda.
- Explicit Python rollback synthesis is no longer supported.
- Rust runtime contracts own deployed behavior; historical Python oracle tests remain visibly
  marked but are not run by CI.
