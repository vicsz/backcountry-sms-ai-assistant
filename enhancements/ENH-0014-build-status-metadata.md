# ENH-0014 — Deterministic build status over SMS

## Status

Implemented locally; Demo deployment and live capture verification pending.

## Objective

Allow an authorized test sender to ask the deployed Rust request runtime which build is serving
requests, without invoking Bedrock, RAG, weather, location, fire-ban, or context adapters.

## Contract

- Exact case-insensitive commands `build`, `status`, `build status`, and `status build` are accepted;
  terminal `?`, `!`, or `.` punctuation is allowed.
- Natural-language messages containing those words are not intercepted.
- The response is `Build <short-git-commit> <UTC-build-time>` and remains within one GSM-7 SMS
  segment.
- Commit and timestamp metadata are embedded during `make -C rust package`; direct test builds
  fail closed with `Build metadata unavailable.` when metadata is absent.
- The command is handled after sender authorization and before context, model, retrieval, or
  provider calls. In live mode only the outbound SMS adapter is used; capture mode sends nothing.
- No latest commit message, mutable counter, secret, or account-specific value is included.

## Non-goals

- No self-incrementing release number.
- No broader health dashboard or provider-status report.
- No changes to Python CDK environment vocabulary or the deferred ingestion paths.

## Acceptance criteria

1. Rust unit/contract tests cover command matching, punctuation/case handling, natural-language
   non-matches, metadata formatting/fallback, GSM-7 length, and the no-adapter early path.
2. `make -C rust package` embeds the current short Git commit and UTC build time in the Lambda
   artifact.
3. Ruff, mypy, full pytest, Rust format/check/test/clippy/package, and CDK synth pass.
4. The Demo target is deployed through the normal explicit SSO/CDK workflow.
5. A redacted direct invocation against the deployed Demo capture target returns the deployed
   commit/time and confirms no model/provider/context calls, no SMS API call, and no SNS publish.

## Deferred follow-up

If a monotonic build number is later needed, use a CI release/run identifier as a separate,
non-authoritative display field rather than adding mutable state to the Lambda runtime.

## Implementing commit

To be recorded after the implementation is committed.
