# ENH-0003 — Rust default, test ownership, and documentation cleanup

## Status

Complete.

## Capability finding

The Demo request path is already deployed as Rust, but the CDK default still requires an explicit
context flag. That makes an ordinary synth or deployment vulnerable to accidentally recreating the
retired Python request Lambda. CI also validates Python and CDK but does not validate the Rust
package, while the Python runtime tests are not clearly separated from CDK/evaluation support.
Several historical Stage 11 and performance notes still read as though Python is the current
request path.

The Ontario Parks RAG MVP has a useful offline evaluator and a read-only live baseline, but its
current evidence shows generic source metadata and weak negative-query discrimination. Freshness,
source-date handling, and recurring ingestion remain deferred and are not part of this enhancement.

## Desired behavior

- The Demo stack defaults to the accepted Rust request runtime. Python is available only through
  an explicit rollback context and is never recreated by an ordinary default deployment.
- CI treats Rust as the runtime test and package owner, retains a separately labelled Python oracle
  gate during the support-code transition, and continues to validate the Python CDK and evaluations.
- RAG documentation distinguishes the current one-time corpus baseline from the deferred work for
  per-section metadata, negative-query handling, freshness, and ingestion.
- Historical documentation is labelled as historical and does not describe Python as the deployed
  request runtime.

## Scope and non-goals

In scope:

- CDK runtime-default and explicit rollback behavior for the Demo target.
- Rust formatting, compilation, tests, clippy, Lambda packaging, and default/rollback CDK synth
  checks in CI.
- Test ownership markers and a concise ownership guide; Rust remains the authoritative runtime
  contract suite, while Python runtime tests are retained as a temporary compatibility oracle.
- Documentation and status wording needed to keep deployment and RAG evidence accurate.

Non-goals:

- Fire-ban ingestion, refresh automation, source polling, or promotion of snapshot status to live
  status.
- Ontario Parks corpus refresh or a new RAG embedding/vector-store deployment.
- Real SMS acceptance traffic.
- Removing the Python CDK, evaluation harness, or retained oracle modules in this change.

## Acceptance criteria

1. A default `BackcountrySmsEchoTest` synthesis contains one Rust request Lambda, an inbound SNS
   subscription to it, and no Python request Lambda.
2. `rust_runtime=false` produces the explicitly documented Python rollback shape; candidate and
   capture contexts remain isolated.
3. CI runs the pinned Rust format/check/test/clippy/package gates, Python lint/type/test gates,
   default Rust CDK synth, and explicit Python rollback synth. Documentation-only changes continue
   to skip runtime validation.
4. Rust runtime contracts are the primary request-path test owner. Python runtime tests are marked
   `legacy_python_runtime` and run as a separate compatibility gate; CDK/evaluation/support tests
   remain in their existing Python locations.
5. RAG documentation records the measured generic-metadata and negative-query limitation and
   explicitly defers freshness/source-date handling and ingestion/refresh work.
6. Stage 11, Rust README, performance, status, and test-ownership wording is consistent with the
   actual deployed Demo state. `git diff --check` passes.

## Implementation

Implemented in the Demo CDK runtime selection, stack tests, CI, Python test markers, the
test-ownership guide, the enhancement register, RAG/Stage 11/performance documentation, and
`STATUS.md`.

## Acceptance and capability tests

- `test_demo_stack_defaults_to_rust_only_request_runtime`
- `test_explicit_python_runtime_context_is_a_rollback_only_path`
- existing candidate/capture isolation tests
- Rust `make fmt`, `make check`, `make test`, `make clippy`, and `make package`
- CI-equivalent default and `rust_runtime=false` CDK synths
- full Python suite, with the legacy oracle reported separately

## Validation results

- Stack tests: 13 passed.
- Python lint/type gates: Ruff passed; mypy passed for 11 files; the negative typing fixture was
  rejected as expected.
- Python suite: 192 passed, 19 skipped. CI-shaped split: 30 non-legacy tests passed and 162 legacy
  oracle tests passed, with 19 expected skips in the non-legacy group.
- Rust: format, locked check, 4 unit tests, 15 integration tests, and clippy passed. The pinned
  Linux release package passed through the configured Zig cross-build path; the unconfigured local
  direct package command correctly reported that the Linux target was not installed.
- CDK: default Rust synth and explicit `rust_runtime=false` rollback synth passed.
- Documentation: `git diff --check` passed.

## Deployment/live-verification status

The current Demo target was already Rust-only from the completed Stage 11 cutover, and the new
no-context synth produces the same Rust-only request shape. No resource-affecting deployment was
needed for this default-selection hardening; a fresh read-only CloudFormation inspection was
attempted but could not run because the local SSO token had expired. No SMS was sent. Fire-ban
ingestion and current-status verification remain deferred.

## Implementing commit

Current commit: `ENH-0003 -- make Rust default and clean up test ownership`.
