# Stage 10.1 — baseline application guardrails

**Status:** Proposed; specification only

## Goal

Add a small, deterministic safety boundary around accepted inbound SMS messages and generated
outbound SMS replies. The MVP should provide credible baseline guardrails before broader user
expansion without creating a separate moderation platform or claiming comprehensive harmful-content
detection.

## Safety claim

The implementation may be described as providing **baseline application guardrails**:

- allowlist enforcement;
- bounded and validated input;
- instruction-safe context handling;
- bounded and validated output;
- safe fallback behavior;
- redacted guardrail telemetry.

It must not be described as comprehensive content moderation, reliable detection of every harmful
request, or a substitute for human judgment in emergencies.

## Scope

Add two explicit policy points to the existing flow:

```text
inbound SMS -> input guardrail -> existing orchestration/Bedrock
             -> output guardrail -> SMS provider
```

The guardrails should be implemented in-process and should not require an additional model call,
network service, or new AWS resource. Where the AI invocation boundary from Stage 10 is present,
the output policy should be applied at the boundary before model text is returned to the SMS
orchestration path.

## Input guardrail contract

Before a message is sent to Bedrock or another downstream operation, the input guardrail must:

- require the existing allowlisted-sender decision;
- reject or safely handle empty input;
- enforce a configured maximum inbound message size;
- handle unexpected control characters and malformed content deterministically;
- preserve the current rule that user content, history, and provider data are data rather than
  application instructions;
- classify obvious unsupported or high-risk requests into a bounded refusal or clarification path
  when a deterministic rule can do so reliably.

The input guardrail must not attempt to infer sensitive user attributes or make a broad semantic
judgment from arbitrary keywords. Unclear cases should continue through the existing safe
clarification or fallback behavior rather than being treated as confirmed unsafe.

An input-blocked message must not invoke Bedrock, location providers, weather providers, or the SMS
send path.

## Output guardrail contract

Before model text is sent as an SMS, the output guardrail must:

- require a non-empty string;
- reject output that is structurally unusable or exceeds the configured SMS bound;
- reject or safely transform characters outside the existing GSM-7 policy;
- prevent raw prompts, internal instructions, provider errors, raw JSON, credentials, account IDs,
  phone numbers, or other internal identifiers from reaching the user;
- reject obvious sensitive-data patterns where deterministic detection is reliable;
- preserve the existing family-safe, concise, non-sensitive response policy;
- return a safe bounded fallback when validation fails.

Existing one-segment SMS normalization may satisfy part of this contract, but the implementation
must make the output safety decision explicit and observable rather than relying only on a string
truncation helper.

An output-blocked response must not be sent to the SMS provider. The fallback itself must pass the
same output-boundary checks.

## Failure and fallback contract

Guardrail failures must use stable, low-cardinality reason codes, such as:

- `empty_input`;
- `input_too_large`;
- `input_malformed`;
- `input_unsupported`;
- `empty_output`;
- `output_too_large`;
- `output_invalid_characters`;
- `output_internal_content`;
- `output_sensitive_content`;
- `guardrail_error`.

Input failures must follow the existing no-provider/no-reply behavior where appropriate, or use a
safe clarification/refusal path when the contract requires a user-facing response. Output failures
must use a short safe fallback and must not expose the rejected output or detection details.

Guardrail code must fail closed for an output that cannot be validated, while keeping guardrail
implementation failures from exposing raw exceptions or sensitive content.

## Privacy and observability contract

Emit only bounded telemetry and traces containing:

- input or output guardrail decision;
- stable reason code;
- logical operation, where available;
- provider and outcome, where available;
- bounded duration and counters.

Do not log or emit message bodies, prompts, model responses, phone numbers, credentials, account
IDs, raw provider errors, or rejected content. Add low-cardinality metrics for blocked inputs,
blocked outputs, and guardrail errors using the repository’s existing telemetry conventions.

## Behavior-preservation requirements

The implementation must preserve:

- allowlist behavior;
- current prompt and history-priority rules;
- existing Bedrock call counts;
- existing location and weather orchestration;
- existing safe fallback messages unless a documented guardrail failure requires a more specific
  bounded fallback;
- one-segment SMS behavior;
- carrier-independent capture mode;
- redacted logging and tracing.

No real SMS, live Bedrock call, or live provider call is required to prove the deterministic
guardrail behavior.

## Testing and acceptance

Tests must verify:

- empty, oversized, malformed, and unsupported inputs follow the input contract;
- blocked inputs do not invoke Bedrock, providers, or SMS sending;
- current SMS content remains data and cannot replace application instructions;
- valid inputs continue through existing orchestration unchanged;
- empty, oversized, malformed, internally revealing, and sensitive-looking outputs are blocked or
  safely handled;
- blocked output never reaches the SMS provider;
- the fallback passes output validation and the one-segment bound;
- guardrail decisions emit reason codes without sensitive content;
- guardrail implementation failures fail safely;
- existing prompt, context, fallback, privacy, evaluation, and capture-mode tests remain valid;
- no additional model call is made solely for guardrail evaluation.

The applicable final validation gate is defined by `development-workflow.md`. This
documentation-only proposal does not itself require Ruff, the full test suite, `cdk synth`, or a
live check.

## Explicit non-goals

This stage does not include:

- Amazon Bedrock Managed Guardrails;
- a second moderation or classifier model call;
- comprehensive toxicity, self-harm, violence, or abuse taxonomy;
- semantic or embedding-based safety classification;
- prompt-injection detection as a complete security solution;
- human review or emergency-response workflows;
- a separate gateway, moderation service, or queue;
- persistent user profiles or sensitive-attribute inference;
- web lookup or tool authorization policy;
- changing the assistant’s user-facing feature scope.

## Completion gate

Stage 10.1 is complete only when explicit input and output guardrail points exist, blocked content
cannot reach the relevant downstream boundary, safe fallbacks are tested, guardrail metrics and
reason codes are redacted and observable, existing behavior-preservation tests pass, the applicable
final validation gate passes, and implementation status is reflected in `STATUS.md`.
