# Stage 10 — application AI invocation boundary

**Status:** Proposed; specification only

## Goal

Create one explicit application-level boundary for model invocation without introducing a new AWS
gateway service or changing the assistant’s user-visible behavior.

The boundary should allow the handler and domain orchestration code to request an AI operation
without depending directly on Amazon Bedrock client details, provider error codes, raw response
shapes, or provider telemetry mechanics.

## MVP boundary

The MVP is an in-process interface and Bedrock-backed adapter:

```text
application orchestration -> AI invocation boundary -> Bedrock adapter -> Bedrock Converse API
```

The boundary covers the existing model operations, including interpretation, advice/synthesis,
general replies, and clarification responses. It is an invocation boundary, not a general-purpose
agent platform.

## Scope

The implementation may refactor the existing Bedrock helper into an explicit interface and
provider adapter. It must provide:

- a typed request containing an operation name, system instruction, current user content, bounded
  history/context, output limits, and generation settings;
- a bounded response containing model text and only safe, optional usage metadata;
- model selection through the existing approved configuration and model allowlist;
- the existing bounded connection timeout and retry behavior;
- stable application-level failure categories rather than provider-specific errors at callers;
- operation-level telemetry and tracing with low-cardinality fields;
- a provider-neutral seam that can be replaced by a test double without network access;
- one documented path for every production model invocation.

The gateway may preserve the existing context-building and output-contract behavior where those
concerns are currently coupled to the model call. It must not weaken current prompt, history,
privacy, or SMS-boundary controls.

## Invocation contract

Each invocation must have:

- a stable operation identifier, such as `interpretation`, `advice`, `general_reply`, or
  `clarification`;
- a bounded input envelope containing the current SMS and only the permitted user-scoped history;
- an explicit maximum output-token setting;
- an explicit temperature or equivalent generation setting;
- a prompt or contract version identifier where one is already available or can be added without
  logging prompt content;
- a configured model selected from the approved model set.

The gateway must return usable model text only after confirming that the provider response contains
one non-empty text result. Domain-specific parsing, such as interpretation-schema validation and
SMS GSM-7/length bounding, may remain outside the gateway unless moving it is required to preserve
the boundary.

## Failure contract

The gateway must map provider and transport failures into the existing bounded application
categories, including where applicable:

- `timeout`;
- `throttled`;
- `access_denied`;
- `service_unavailable`;
- `malformed_output`;
- `unknown`.

Callers must not need to inspect a raw Bedrock `ClientError`, SDK response, prompt, model output,
or provider payload to choose a fallback. Raw provider details remain available only to local
debugging where explicitly permitted and must not enter production logs, telemetry, or SMS.

An invocation failure must not cause the gateway to start an unrelated second reasoning flow. Any
provider retries remain bounded within the existing dependency and Lambda timeout budgets.

## Observability contract

For every attempted invocation, emit bounded telemetry and tracing that can answer:

- which logical operation ran;
- whether it succeeded or failed;
- which provider was used;
- which stable failure category occurred, if any;
- call duration and, when safely available, bounded usage evidence;
- whether the invocation was a retry or final attempt, if that distinction is exposed.

Do not record phone numbers, message bodies, prompts, model responses, raw provider errors,
credentials, account IDs, or unbounded context. Telemetry must use existing low-cardinality metric
and span conventions.

## Behavior-preservation requirements

The refactor must preserve:

- the existing model and inference-profile configuration;
- the existing number of logical Bedrock calls per message;
- the existing two-call weather interpretation/synthesis flow;
- the existing bounded user-scoped context behavior;
- existing failure categories and safe fallback messages;
- existing prompt/output contracts;
- existing one-segment SMS behavior;
- existing redacted logging and tracing behavior;
- the carrier-independent capture-mode behavior.

No live SMS, deployment, or live Bedrock/provider call is required to prove the refactor itself.

## Testing and acceptance

Tests must verify:

- the Bedrock adapter invokes the configured provider using the expected bounded request;
- callers use the invocation boundary rather than constructing a Bedrock client directly;
- a provider test double can exercise success and failure paths without network access;
- every supported operation emits the expected operation-level telemetry metadata;
- empty and malformed provider responses map to the existing safe failure behavior;
- timeout, throttling, access, and service-unavailable failures map consistently;
- retry behavior remains bounded and does not create an unrelated second reasoning flow;
- interpretation and synthesis retain their existing call count and context contracts;
- no sensitive content appears in logs, traces, metrics, or exception messages exposed to callers;
- existing unit and evaluation tests remain unchanged in meaning;
- carrier-independent capture mode remains available without sending SMS.

The applicable final validation gate is defined by `development-workflow.md`. This
documentation-only proposal does not itself require Ruff, the full test suite, `cdk synth`, or a
live check.

## Explicit non-goals

This stage does not include:

- a new API Gateway, Lambda, queue, or standalone AI gateway service;
- web search or internet lookup;
- tool calling or autonomous agent orchestration;
- managed Bedrock Guardrails or application guardrail policy;
- multi-provider routing or automatic model substitution;
- semantic routing or embedding-based retrieval;
- persistent user memory or profile inference;
- prompt-management infrastructure;
- automatic deployment or release workflow changes;
- changing model prompts, response policy, SMS limits, or user-facing features.

## Completion gate

Stage 10 is complete only when the application has one tested invocation boundary for all production
model calls, the Bedrock adapter is the only production provider implementation, behavior-preservation
tests pass, privacy and observability checks pass, the applicable final validation gate passes, and
the implementation status is reflected in `STATUS.md`.
