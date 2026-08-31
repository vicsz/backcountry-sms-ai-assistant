# Stage 2 — Bedrock SMS assistant MVP

## Purpose

Replace the Stage 1 fixed echo with one bounded Bedrock response while preserving the existing
allow-list and SMS delivery path. The primary demo input is `tell me a joke`, but every message
from the allow-listed sender enters the same tiny-assistant path.

## Contract

- Model: `amazon.nova-2-lite-v1:0`, invoked through the `us.amazon.nova-2-lite-v1:0`
  inference profile with `bedrock-runtime.converse` in `ca-central-1`. The inference profile is
  required because the foundation model does not support direct on-demand invocation.
- Model ID is configurable through `BEDROCK_MODEL_ID`, defaulting to the model above.
- A fixed system prompt requires concise, family-safe, non-sensitive, useful responses.
- Exactly one Bedrock call is made for each allow-listed inbound message.
- The application sends at most one SMS segment (160 characters).
- Empty, malformed, unavailable, throttled, timed-out, and access failures map to short,
  safe, category-specific fallback messages; raw provider errors are never sent by SMS.
- Unapproved senders produce no Bedrock call and no SMS reply.
- Logs record only redacted outcomes and failure reason codes; never log phone numbers, message
  bodies, credentials, raw provider errors, or model output.

## Explicit non-goals

Weather, memory, tools, DynamoDB, managed Bedrock Guardrails, production access, and multi-turn
conversation state are deferred.

## Acceptance examples

1. An allow-listed `tell me a joke` message receives one concise model-generated SMS.
2. An allow-listed arbitrary short message receives one concise assistant response.
3. A long model response is bounded to one SMS segment.
4. A Bedrock error or unusable response receives the mapped fallback for its failure category.
5. An unapproved sender receives no reply and does not invoke Bedrock.
