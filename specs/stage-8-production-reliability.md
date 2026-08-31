# Stage 8 — production reliability and operational readiness

**Status:** Proposed; documentation-only specification

## Goal

Reduce and explain the observed burst `SMS ServiceQuotaExceededException` failures while keeping
the current SNS → Lambda → dependency calls → SMS design bounded, cost-aware, and diagnosable.
Retain a change only when real before/after data demonstrates better outcomes.

## Scope

- Establish a baseline for SMS quota failures, burst shape, retries, latency, and cost.
- Compare bounded pacing/retry and queue alternatives for outbound SMS, including delivery,
  duplicate, delay, operational, and cost implications.
- Make SMS delivery an independently observable phase, separate from the two-call Bedrock weather
  workflow: interpretation followed by synthesis.
- Add live-evaluation preflight for configuration, access, quotas, mode, and cost limits. Evaluation
  runs must not send SMS.
- Produce redacted, comparable reports and an evidence-based recommendation.

## Non-goals

No application implementation, deployment, quota request, provider migration, or production queue
is implied. Do not change the two-call Bedrock contract, prompts, safety behavior, history,
location, or weather functionality. Do not create a transcript store, log unbounded payloads, or
generate synthetic SMS traffic. No live call or SMS send may be hidden in CI.

## Proposed experiments

Predeclare the hypothesis, version, sample size, exclusions, cost limit, and stop conditions for
each small, explicitly approved experiment.

1. Baseline the current direct-send path under normal and bounded burst conditions, using only the
   traffic needed to characterize the observed failure.
2. Evaluate a small maximum-attempt retry policy for quota/throttling errors only, with exponential
   backoff, jitter, an overall deadline, idempotency protection, and no retry of permanent errors.
3. Evaluate conservative send-rate pacing or a token bucket, measuring queueing delay and quota
   failures.
4. If separately approved, evaluate durable buffering with one controlled consumer, expiry, and a
   DLQ. Compare it with direct send; do not introduce it without measured benefit.

Retain a change only if its predeclared gate passes: lower failure rate without unacceptable p95
latency, duplicate risk, operational burden, or incremental cost.

## Telemetry/reporting

Emit redacted correlation data and phase timing for receipt/idempotency; each Bedrock call;
location/weather dependencies; and SMS enqueue/send attempts, quota category, retry or pacing
delay, final outcome, and provider delivery status where available. Report like-for-like p50/p95
end-to-end and phase latency, failure rate by category, retries, duplicates/expiry, sample size,
cold/warm context, configuration identifiers, and estimated AWS/provider cost. Include uncertainty,
missing telemetry, and the accept/reject rule. Never include content, phone numbers, credentials,
account IDs, or raw provider payloads.

## Tests

Unit-test quota classification, retry limits, backoff/deadline, pacing bounds, idempotency,
expiry/DLQ decisions if approved, and telemetry contracts. Test that the Bedrock calls remain
distinct and an SMS failure is not reported as a Bedrock failure (or vice versa). Live
Bedrock/provider/SMS checks are opt-in and outside the default suite; no fixture, hook, or CI step
may make a hidden live call or send SMS.

## Live verification

Before an opted-in live evaluation, require a human-reviewed preflight covering AWS profile/region,
model and inference-profile access, SMS sandbox/allow-list state, quota assumptions, log/metric
destinations, tracing sample rate, budget limit, run mode, sample size, and explicit
`SMS_ENABLED=false`. Abort on missing or unsafe configuration. Any production SMS check is a
separate named acceptance action, never an evaluation side effect.

## Acceptance gates

- The observed exception is reproduced or bounded with evidence, with scope and uncertainty recorded.
- Baseline and every retained alternative have comparable p50/p95, failure-rate, retry, latency,
  duplicate/expiry, and cost measurements.
- Selected behavior has explicit limits, idempotency, timeout/dead-letter handling as applicable,
  redacted telemetry, and operator guidance.
- Bedrock interpretation, Bedrock synthesis, and SMS delivery are independently diagnosable.
- Preflight and no-hidden-live-call CI checks pass.
- No change is retained on intuition, a single lucky run, or a latency gain that worsens failures,
  duplicates, unsafe behavior, or cost beyond the approved bound.

## Delivery constraints

This is documentation-first. Any implementation requires a narrowly scoped follow-up, offline
tests, explicit experiment and cost/risk approval, and separate deployment approval. Authoring and
reviewing this spec must not deploy, make live calls, or send SMS.
