# Testing ownership

The Rust suite under `rust/tests/` owns the deployed request-path contract: event parsing, delivery
guards, interpretation validation, routing, retrieval grounding, context behavior, bounded SMS
output, failure fallbacks, and the adapter call path represented by deterministic fakes. The Rust
contract suite is the required place to add coverage for deployed behavior.

Python remains the implementation language for CDK and the evaluation/support tooling. The former
Python request-runtime test file is marked `legacy_python_runtime`. It is retained as
historical reference while selected support modules remain in the repository, but it is not run by
CI and is not the authoritative definition of deployed request behavior. The Python handler and related modules
remain only where evaluation or offline support explicitly requires them; CDK no longer creates a
Python request or capture Lambda.

CI therefore runs the retained Python support groups alongside the Rust contract gate:

- the Python gate for CDK, evaluations, ingestion, and support behavior;
- no Python request-runtime gate.

The Rust gate runs formatting, locked dependency checks, unit/integration tests, clippy with warnings
as errors, and the release Lambda package build. A Rust behavior change should add or update Rust
contract coverage first. Python oracle coverage should only be changed when it documents a support
boundary or preserves a useful parity check.

The following remain intentionally separate from ordinary tests: live Bedrock/provider calls,
ingestion or refresh operations, deployed capture checks, and real SMS sends.

The retained Python request modules are offline support/reference code, not a second deployed path.
The normal CDK target rejects the former `rust_runtime=false` rollback switch and the former
`python_capture` context. Removing the retained Python modules themselves is a separate cleanup
because the evaluation and support tests still import selected helpers.
