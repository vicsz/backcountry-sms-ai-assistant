# Stage 7.1 — Bedrock model evaluations

**Status:** Complete; offline and Bedrock-live evaluations passing

## Goal

Create a repeatable evaluation suite for the Bedrock calls used by the assistant. The suite must
show whether the model correctly classifies intent, extracts a current location, uses permitted
history, preserves coordinates, and produces bounded responses.

## Scope

Use versioned JSON or YAML fixtures containing an ID, description, ordered user-scoped history,
current SMS, expected structured interpretation, and expected response behavior. Current message
and history order must be explicit; no hidden global state or implicit file ordering.

The suite covers:

- current whereabouts supplying the weather location;
- current location replacing an older historical location;
- a location-free follow-up inheriting the newest permitted location;
- an explicit return to an older location;
- named locations such as Toronto, NYC, Burnt Island Lake, and Portage Store;
- noisy and invalid GPS coordinates;
- missing, ambiguous, malformed, empty, timed-out, throttled, and access-denied model responses;
- arbitrary short non-weather input;
- synthesis output bounded to one GSM-7 SMS segment.

The model suite mocks geocoding, weather, DynamoDB, and SMS. It must not call providers or send
messages.

## Execution modes

### Offline (default)

Use deterministic Bedrock fakes. Assert orchestration, request envelopes, prompt selection,
history ordering, call counts, fallbacks, schema validation, and SMS bounds. Offline runs must be
network-free and deterministic.

### Bedrock-live (opt-in)

Call the configured Bedrock inference profile using public, synthetic fixtures and mocked location,
weather, DynamoDB, and SMS adapters. Bound the fixture count, prompt size, output size, and model
calls. Identify the model ID, inference profile, and run mode in the result. No production data or
SMS is permitted.

The suite must never silently fall back from Bedrock-live to offline behavior.

## Deterministic assertions

Every applicable scenario asserts:

- valid structured JSON and exactly the expected schema keys;
- intent classification;
- `location_text`, `current_location_text`, and `location_source`;
- current-message precedence over history;
- correct newest-history selection for follow-ups;
- exact current-SMS coordinates and rejection of invented coordinates;
- configured model ID, fixed prompt, and bounded token settings;
- expected Bedrock call count and order;
- fixed behavior for malformed output and dependency failures;
- one GSM-compatible SMS segment;
- no sensitive data in prompts, logs, or result artifacts.

Assertions inspect structured adapter inputs and outputs. Exact generated prose is not required
unless the scenario specifies a fixed fallback or protocol string.

## Optional LLM judge

The judge is a separate, explicitly opt-in evaluation step. It receives only the fixture, the
assistant’s structured result or bounded reply, and provider facts declared by the fixture. It must
not receive credentials, account IDs, phone numbers, production history, or unbounded logs.

The judge returns schema-validated JSON with a `0`–`2` score, concise reasons, an overall pass, and
an uncertainty flag. Suggested dimensions are intent fit, current-location interpretation,
newest-location use, faithfulness to supplied facts, safety, concision, and context use.

Deterministic assertions are authoritative. The judge may not approve invented coordinates, wrong
location sources, sensitive-data exposure, malformed output, or one-segment violations. Offline
judge runs use a deterministic stub; a real judge is explicitly identified and opt-in.

## Runner and acceptance

Provide one explicit mode-selecting command, for example:

```text
pytest -m eval_model --eval-mode=offline
AWS_PROFILE=backcountry-dev pytest -m eval_model --eval-mode=bedrock-live --aws-region=ca-central-1
```

Live modes require `--aws-region` and fail before test collection or any AWS call when it is
missing. The region is applied to both `AWS_REGION` and `AWS_DEFAULT_REGION` for the run. The
AWS profile remains an explicit environment setting; the harness does not select credentials.

Acceptance requires deterministic offline coverage for current-location precedence, follow-up
context, NYC/Toronto wording, GPS preservation, malformed responses, and bounded output. Existing
unit tests and application behavior must remain unchanged.

## Non-goals

No real geocoder calls, real weather calls, SMS acceptance, provider ranking, deployment decisions,
long-term transcript storage, or automatic model changes.
