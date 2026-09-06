# Testing ownership

The Rust suite under `rust/tests/` owns the deployed request-path contract: event parsing, delivery
guards, interpretation validation, routing, retrieval grounding, context behavior, bounded SMS
output, failure fallbacks, and the adapter call path represented by deterministic fakes. The Rust
contract suite is the required place to add coverage for deployed behavior.

Python remains the implementation language for CDK and the evaluation/support tooling. The former
Python request-runtime test file, Lambda entrypoint, SMS client, and DynamoDB context-store module
have been removed. `backcountry_sms.support` remains only as an offline/evaluation helper surface;
it is not a deployed request path.

CI therefore runs the retained Python support groups alongside the Rust contract gate:

- the Python gate for CDK, evaluations, ingestion, and support behavior;
- no Python request-runtime gate.

The Rust gate runs formatting, locked dependency checks, unit/integration tests, clippy with warnings
as errors, and the release Lambda package build. A Rust behavior change should add or update Rust
contract coverage first. Python oracle coverage should only be changed when it documents a support
boundary or preserves a useful parity check.

The following remain intentionally separate from ordinary tests: live Bedrock/provider calls,
ingestion or refresh operations, deployed capture checks, and real SMS sends.

The retained Python provider, retrieval, fire-ban, ingestion, telemetry, tracing, and model modules
are offline support/reference code, not a second deployed path. The normal CDK target rejects the former `rust_runtime=false` rollback switch and the former
`python_capture` context. Removing the retained Python modules themselves is a separate cleanup
because the evaluation, ingestion, and offline-support tests still import selected helpers.
