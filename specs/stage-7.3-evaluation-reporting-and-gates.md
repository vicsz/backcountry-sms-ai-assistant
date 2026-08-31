# Stage 7.3 — evaluation reporting, metrics, and gates

**Status:** Implemented locally; report and deterministic-gate work complete

## Goal

Make Stage 7 evaluation results comparable, reviewable, and safe to use in development and release
decisions without creating a production transcript store or a heavyweight external evaluation
platform.

## Scope

Consume results from the model and provider evaluation suites and produce a human-readable terminal
summary, a machine-readable JSON report per run, one result record per scenario, deterministic
pass/fail results separate from optional judge results, model/provider and fixture/configuration
identifiers, bounded latency/usage evidence, and a final status suitable for CI or release review.

Reports are local development artifacts under a run-specific directory such as
`local/evaluations/<run-id>/` and must be excluded from version control. No report may contain
credentials, account IDs, phone numbers, production message history, secrets, or unbounded logs.

## Report contract

Each scenario result contains, where applicable:

- run ID, suite, mode, scenario ID, and fixture version;
- model ID or provider name;
- deterministic assertion results and failure reasons;
- optional judge result, score, reasons, and uncertainty;
- Bedrock call count and configured token bounds;
- input/output size evidence where available;
- provider candidate count and selected result;
- latency per operation and total scenario latency;
- estimated cost only when usage data and rates are known;
- final pass/fail state.

Exact generated prose is not required in the durable report. Any retained debugging output must be
bounded, synthetic, and explicitly separated from the durable summary.

## Cost and latency tracking

For Bedrock-live runs, record actual usage metadata when the service provides it. Otherwise record
call count, input/output sizes, configured maximum tokens, and `estimated_cost: null`; do not invent
precise dollar values.

Track interpretation, synthesis, optional judge, provider lookup, and total scenario latency
separately. The report must make accidental extra model calls visible.

## CI thresholds

Hard CI gates apply only to deterministic offline runs initially:

- schema validity: 100%;
- current-location precedence: 100%;
- correct permitted-history selection: 100%;
- no invented or altered coordinates: 100%;
- expected Bedrock call count: 100%;
- one-segment SMS bound: 100%;
- offline mode makes zero network calls;
- no sensitive-data leakage in reports or logs.

Live model and provider suites remain explicit manual or scheduled checks until their fixtures and
provider/model behavior are stable across repeated runs. Latency, judge scores, and provider
candidate changes are initially report-only, not automatic blockers.

## Automated gates

The gate must fail independently for deterministic failures and judge failures. A judge may not
override a deterministic failure involving schema, safety, coordinates, location source, privacy,
call count, or SMS bounds.

Release or demo readiness may require a bounded live matrix covering current-location wording,
history precedence, Burnt Island Lake, Portage Store, Toronto, and NYC. Live SMS acceptance remains
outside this harness and must remain an explicit separate action.

## Runner and acceptance

Provide a report-producing command, for example:

```text
pytest -m 'eval_model or eval_location' --eval-mode=offline --eval-report-dir=local/evaluations/<run-id>
```

Acceptance requires a stable JSON schema, redaction checks, deterministic/offline gates, clear
separation of judge and deterministic results, and reports that can be compared between runs.
Existing unit tests and application behavior must remain unchanged.

## Non-goals

No production telemetry pipeline, long-term conversation storage, automatic deployment, automatic
model migration, AWS budget enforcement, or mandatory live calls in CI.
