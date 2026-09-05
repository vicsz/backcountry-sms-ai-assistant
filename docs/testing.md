# Testing ownership

The Rust suite under `rust/tests/` owns the deployed request-path contract: event parsing, delivery
guards, interpretation validation, routing, retrieval grounding, context behavior, bounded SMS
output, failure fallbacks, and the adapter call path represented by deterministic fakes.

Python remains the implementation language for CDK and the evaluation/support tooling. The former
Python request-runtime tests are marked `legacy_python_runtime`. They are retained as a temporary
compatibility oracle while the support modules remain in the repository, but they are not the
authoritative definition of deployed request behavior.

CI therefore runs two visibly separate Python groups:

- the normal Python gate for CDK, evaluations, and support behavior;
- the `legacy_python_runtime` compatibility gate for retained Python runtime modules.

The Rust gate runs formatting, locked dependency checks, unit/integration tests, clippy with warnings
as errors, and the release Lambda package build. A Rust behavior change should add or update Rust
contract coverage first. Python oracle coverage should only be changed when it documents a support
boundary or preserves a useful parity check.

The following remain intentionally separate from ordinary tests: live Bedrock/provider calls,
ingestion or refresh operations, deployed capture checks, and real SMS sends.

The retained Python request modules are a rollback/oracle boundary, not a second deployed path.
Removing them requires a separate post-cutover decision with a preserved artifact and rollback
evidence; this cleanup does not silently delete the CDK, ingestion, or evaluation tooling.
