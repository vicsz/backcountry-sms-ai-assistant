# Stage 5 — short-lived message context

**Status:** Complete; deployed and verified

## Goal

Provide short-lived message context so an allow-listed user can ask a follow-up without repeating
information such as the location. Keep this MVP limited to recent SMS content and the minimum
metadata required to retrieve it.

## Design boundary

This stage has one concern: **bounded message context**. Operational logs remain redacted and are
not supplied to the LLM.

## Conversation behavior

- Every request is associated with an allow-listed sender and a short-lived user context.
- If a follow-up omits information that appeared in recent context, the LLM may use that bounded
  context.
- If the required context is absent or expired, ask the user to provide it again rather than
  guessing.
- Conversation history is bounded to a small recent window and a short TTL (for example, 24 hours
  or 7 days; choose one before implementation).
- The LLM receives only the bounded recent messages required for the current request. It does not
  receive operational telemetry or raw provider payloads.
- Context is always scoped to the requesting user's normalized phone number; never mix users.
- Retrieve only the most recent configured number of interactions (for example, the last 5).
- Before every Bedrock call, build a bounded context containing the current inbound SMS plus those
  prior interactions, including both their input and output text.
- Clearly label the current message as current and older rows as history so the model does not treat
  stale instructions as the new request.
- Preserve the existing two-call weather pattern: one interpretation call followed by one advice
  synthesis call. Do not add an extra Bedrock call solely for history.

## Interaction record

```text
user_phone_e164      # partition key; protected PII
message_id            # SNS message ID; idempotency key
input_body            # inbound SMS; encrypted at rest; never logged
output_body           # outbound SMS; encrypted at rest; never logged; may be empty
created_at             # sort key
ttl
```

Use one row per accepted interaction because an input normally produces one output. The output may
be empty for an in-progress, failed, or deliberately suppressed reply. Store only allow-listed
traffic. Normalize the sender to E.164 before storage and querying. The phone number is necessary
for user-specific context, so protect it with DynamoDB encryption at rest, least-privilege access,
and the selected TTL; never expose it in application logs or LLM prompts.

## Privacy and safety

- Never log message bodies, prompts, model responses, phone numbers, secrets, or raw provider data.
- Encrypt DynamoDB data at rest and restrict reads to the Lambda role and an explicitly approved
  operator path.
- Use the shortest useful TTL; default proposal is seven days for messages.
- Do not retain rejected/unapproved message bodies.
- Document deletion and access behavior before deployment.

## Reliability and idempotency

- Context writes must never prevent an SMS reply.
- A write failure is recorded as a redacted outcome and processing continues.
- Use the SNS message ID as the idempotency key for inbound message records.
- Duplicate deliveries must not duplicate history or cause duplicate Bedrock calls.

## DynamoDB shape

- Use one on-demand table with `user_phone_e164` as the partition key and `created_at` plus
  `message_id` as the sort key.
- Enable TTL on every retained item.
- Add only the required `PutItem`, `Query`, and conditional-write permissions. Query in descending
  order with a hard limit for the most recent X interactions.
- Resource tags are required.
- No dashboard or user-facing transcript browser in this stage.

## Bedrock context contract

For every Bedrock invocation (interpretation or synthesis), the request builder must include:

1. The current inbound SMS.
2. Up to the configured number of that user's most recent unexpired interaction rows.
3. Both `input_body` and `output_body` for each history row, in chronological order.
4. A fixed instruction that history is context only and the current message has priority.

The interpretation call returns structured intent, time window, activity, and location selection.
It may select a location from the current message or bounded history and must identify the source
message. Named-place coordinates still require provider validation; the model may not invent them.
The synthesis call receives the verified location, structured weather facts, deterministic guidance,
and the same bounded history.

Conversational location rules supplied to the interpretation prompt:

- An explicit location in the current message takes priority.
- A message such as `I'm now at Portage Store` replaces the older location.
- A follow-up such as `What about tomorrow?` inherits the newest relevant location.
- Older locations are used only when the user explicitly refers back to them.
- Coordinates are never inherited from history. Only coordinates explicitly present in the
  current SMS may be used directly; a named place selected from history still requires provider
  validation.

This allows a sequence such as:

```text
User: Weather at 45.62,-78.42 tonight
Assistant: ...weather reply...
User: What about tomorrow?
```

The final request can use the previous location because it is present in the bounded history. If
the relevant context is outside the retention window, the assistant asks for the location again.

## Acceptance criteria

- An accepted message creates one interaction record containing its input and eventual output,
  partitioned by the normalized sender number.
- A follow-up uses only unexpired bounded message context.
- A follow-up after expiry asks for the missing information again.
- A user query returns only that user's most recent configured number of interactions.
- Both Bedrock calls receive the current message and the same bounded, user-scoped prior history.
- The interpretation call identifies the selected location and source message before provider lookup.
- A follow-up such as `What about tomorrow?` can use a location present in the retained prior SMS.
- Expired or absent history is not supplied to Bedrock.
- Input and output bodies are available to the LLM only through the bounded context builder and never through
  logs or operational telemetry.
- Duplicate SNS delivery is idempotent.
- DynamoDB failure does not prevent a safe SMS reply.
- TTL and encryption behavior are tested.
- Existing one-segment SMS and redacted logging controls remain unchanged.

## Explicit non-goals

- Long-term memory or user profiles.
- Cross-user context or sharing context between phone numbers.
- Location caching or weather-result caching.
- Provider-status fields in message context.
- Analytics dashboards, transcript browsing, or autonomous alerts.
