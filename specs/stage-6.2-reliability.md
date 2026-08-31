# Stage 6.2 — reliability and dependency resilience

**Status:** Complete; deployed and live normal-path verification recorded

## Goal

Ensure one inbound SMS produces at most one intentional reply, does not hang on external services,
and gives a predictable fallback when a dependency fails.

## Scope

This MVP covers only:

- dependency timeouts and failure mapping;
- bounded retries for transient failures;
- SNS idempotency;
- partial-failure behavior.

Observability, tracing, security hardening, circuit breakers, and automated remediation remain
separate concerns.

## Dependency failure contract

Every external call must have an explicit timeout, a stable failure category, and a safe
continuation or fallback. No dependency may wait indefinitely.

Initial proposed limits are configurable defaults:

- Bedrock: 8 seconds;
- geocoding and weather: 5 seconds;
- DynamoDB context: 2 seconds;
- SMS publish: 5 seconds.

Timeout configuration must leave enough budget for the Lambda handler to finish its bounded
fallback path.

## Retry contract

Retry only transient failures:

- throttling;
- temporary network errors;
- retryable HTTP 5xx responses.

Use no more than two retries with short exponential backoff. The complete processing attempt must
remain within the Lambda timeout.

Do not retry access denied, malformed responses, invalid requests, missing model access, or other
non-retryable HTTP 4xx responses.

One logical Bedrock or provider operation may have retries, but a retry must not start an unrelated
second reasoning flow or replay the full message pipeline.

## SNS idempotency contract

Use the SNS message ID as the inbound idempotency key. A duplicate delivery must not:

- call Bedrock again;
- call geocoding or weather again;
- write a second context record;
- send a second SMS reply.

The idempotency record must be created before processing or protected by a conditional write. If
idempotency storage is unavailable, fail safely rather than risk duplicate user-visible replies.

## Partial-failure contract

| Failure point | Required behavior |
|---|---|
| Context read | Continue without history and record a bounded failure outcome |
| Intent call | Send the intent/AI-unavailable fallback |
| Location lookup | Ask for clearer location or GPS coordinates |
| Weather call | Send the weather-unavailable fallback |
| Synthesis call | Send a short provider-facts fallback when safe; otherwise use the AI-unavailable fallback |
| Context write | Do not block the current reply |
| SMS send | Record the failure; do not retry the entire message flow |

A later failure must never restart earlier stages. Existing two-call weather behavior remains the
logical flow; this spec only defines how failures and retries behave within it.

## Failure categories

Use stable, bounded categories for handling and operational telemetry, such as:

- `timeout`;
- `throttled`;
- `access_denied`;
- `invalid_request`;
- `malformed_response`;
- `provider_unavailable`;
- `storage_unavailable`;
- `sms_send_failed`.

Do not expose raw exception text, provider payloads, prompts, model output, phone numbers, or
credentials in replies or logs.

## Testing and acceptance

Tests must verify:

- each dependency timeout maps to the correct fallback;
- retryable failures retry at most twice;
- non-retryable failures are not retried;
- duplicate SNS events produce one Bedrock call sequence and one SMS reply;
- duplicate deliveries do not create duplicate context records;
- partial failures do not restart earlier stages;
- context-storage failure does not prevent a safe reply;
- total processing remains within the Lambda timeout budget;
- existing SMS length, privacy, observability, tracing, and fallback contracts remain unchanged.

The live acceptance check should use a public test message and deliberately exercised failure
fixtures or test doubles. It must not depend on sending duplicate production SMS messages.

## Completion gate

Stage 6.2 is complete only when Ruff, the full unit suite, and `cdk synth` pass; timeout and retry
configuration is deployed; idempotency and partial-failure tests pass; and a live smoke check
confirms one safe reply under normal operation.

## Non-goals

No circuit breakers, queue-based workflow orchestration, automated remediation, multi-region
failover, advanced retry libraries, or new user-facing features.
