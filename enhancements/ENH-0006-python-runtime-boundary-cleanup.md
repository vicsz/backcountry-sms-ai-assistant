# ENH-0006 — Python runtime boundary cleanup

## Status

Complete for the current cutover boundary; source retirement remains intentionally deferred.

## Decision

Rust owns the deployed request path. Python remains only where it is still needed for CDK,
deployment helpers, fire-ban/RAG offline tooling, and the explicitly labelled rollback/oracle
surface. The Python Lambda is not part of the default Demo stack and is not subscribed to inbound
SNS.

## Cleanup completed

- Test ownership is documented in [`docs/testing.md`](../docs/testing.md).
- The default CDK path and CI gates are Rust-first; the Python runtime path is an explicit rollback
  shape only.
- RAG and fire-ban support modules are kept because their local/offline capabilities are still
  active and because the rollback path has not yet been retired.

## Remaining safe cleanup

After a further observed Rust-only window and an explicit decision to remove rollback, delete the
Python request-runtime implementation and its oracle tests in a separate change. Do not remove it
as part of a documentation or support-tool change, and do not remove Python CDK/support code.

## Acceptance

- Default Demo synthesis contains Rust only for the request Lambda.
- Explicit Python rollback synthesis remains testable.
- Rust runtime contracts and the retained Python oracle are visibly separated in CI.
