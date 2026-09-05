# Stage 9.3.2 — Ontario provincial parks RAG MVP

Status: Implemented locally; deployment, one explicit ingestion sync, and any redacted live retrieval smoke test remain opt-in.

## Objective

Add a bounded RAG path over the one-time
`data/rag/ontario-provincial-parks-guide.md` corpus. The MVP must answer practical, source-backed
questions about Ontario provincial parks and return uncertainty or a redirect when the guide does
not contain the answer.

## User stories and use cases

- As a camper, I want to ask what activities and facilities a named provincial park offers.
- As a trip planner, I want to know whether a park supports car, walk-in, group, winter, or
  backcountry camping.
- As a visitor, I want a concise summary of what to know before visiting a named park.
- As a paddler or hiker, I want practical planning information for a park when it is present in the
  guide.
- As a user comparing parks, I want to ask which parks match a stated activity or facility, subject
  to the guide’s documented coverage.
- As a safety-conscious user, I want current fire bans, closures, weather, reservations, and
  availability questions routed away from the static RAG corpus rather than answered from stale
  text.

Representative supported questions include:

- “Does Killarney have backcountry camping?”
- “What facilities are listed for Arrowhead?”
- “Which Ontario parks mention canoeing and boat launches?”
- “What kind of camping does this park support?”
- “What should I know before visiting this park, based on the guide?”

Representative unsupported or redirected questions include:

- “Is Algonquin under a fire ban today?”
- “Is the park open tomorrow?”
- “Are campsites available this weekend?”
- “Is this trail or access point currently closed?”
- “What is the weather there?”

## Retrieval and response contract

- Use only the one-time Markdown corpus as the initial RAG knowledge source.
- Retrieve a small bounded number of relevant chunks and preserve park name, section, and source URL
  metadata.
- Keep retrieval, prompt size, model calls, timeout, and output to the existing one-segment SMS
  boundary.
- Answer only from retrieved evidence. If evidence is absent, conflicting, or too weak, say that
  the guide does not establish the answer.
- Preserve the distinction between an official park fact and general planning advice.
- Include a concise source label or URL where feasible.
- Do not use RAG output to establish current legal, operational, weather, fire-ban, closure,
  reservation, fee, or availability status.
- Keep RAG failure independent from weather and Stage 9.2 fire lookup behavior.

The handler may use deterministic intent selection for explicit park-information questions. An LLM
may help classify relevance, but it may not invent park attributes or override the current-status
boundary.

## MVP AWS configuration

- Use Amazon Bedrock Knowledge Bases in the application deployment region, expected to be
  `ca-central-1`. Do not add cross-region retrieval for this MVP.
- Create one Knowledge Base with one S3 data source containing only
  `data/rag/ontario-provincial-parks-guide.md`.
- Use `amazon.titan-embed-text-v2:0` embeddings and the managed vector-store option supported by
  the selected Knowledge Base setup. OpenSearch Serverless is the default if an explicit vector
  store is required.
- Use fixed chunking at 300 tokens with 30-token overlap. Do not add semantic chunking or a custom
  parser until evaluation shows that fixed chunks lose useful park-section context.
- Trigger one explicit data-source sync after the object is uploaded. This is a one-time snapshot
  load, not ongoing maintenance; scheduled ingestion, source polling, automatic refresh, and
  freshness enforcement for hours, rentals, operating dates, fees, reservations, or availability
  remain deferred to a future ingestion/refresh stage.
- Record the Knowledge Base/data-source identifiers, embedding model, chunking settings, source
  object version or SHA-256, and deployment region in implementation documentation or stack outputs.
  Do not commit account-specific IDs or generated AWS configuration.

The first implementation may use the Bedrock `Retrieve` API and pass returned excerpts to the
existing bounded response-generation call. It does not need `RetrieveAndGenerate` or a separate
conversational agent.

## Handler intent and routing contract

Extend the interpretation schema with `information_lookup`. The existing intents remain
`weather`, `fire_status`, `general`, and `unclear`.

- Select `information_lookup` for stable guide facts such as activities, facilities, camping types,
  or basic planning context.
- Keep current-status requests on their existing live paths: fire-ban questions use `fire_status`,
  weather questions use `weather`, and closure/opening/reservation/availability requests receive a
  deterministic redirect or `unclear` response.
- A named park is preferred but not required for a bounded comparison query.
- For `information_lookup`, perform one bounded Knowledge Base retrieval followed by one bounded
  response-generation call. Do not perform weather, geocoding, fire-ban, or reservation lookups.
- Preserve existing idempotency, history, timeout, telemetry, and one-segment SMS contracts.
- If retrieval fails, times out, returns no useful result, or exceeds the configured limit, return a
  short deterministic fallback. Never silently fall back to an uncited general answer.

The response prompt receives only the user question and retrieved excerpts/citation metadata. It
must answer from those excerpts, identify the park where possible, and include a compact source label
such as `Source: Ontario Parks — <park name>`. Include a URL when it fits the SMS bound.

## MVP offline evaluation set

The test fixtures use representative retrieved excerpts and do not require the real AWS Knowledge
Base. At minimum, cover:

| Question | Expected behavior |
| --- | --- |
| “Does Killarney have backcountry camping?” | `information_lookup`; answer only from the Killarney excerpt and cite it. |
| “What facilities are listed for Arrowhead?” | `information_lookup`; summarize listed facilities without adding amenities. |
| “Which Ontario parks mention canoeing and boat launches?” | `information_lookup`; return only parks supported by retrieved evidence. |
| “What should I know before visiting Algonquin based on the guide?” | `information_lookup`; summarize stable facts and state that current details must be verified. |
| “Is Algonquin under a fire ban today?” | `fire_status` or live redirect; never answer from RAG. |
| “Is the park open tomorrow and are sites available?” | Redirect or `unclear`; no RAG answer. |
| “Does NeverListed Park have winter camping?” | Bounded uncertainty; do not guess. |
| Any supported question with empty, irrelevant, conflicting, timed-out, or failed retrieval | Deterministic bounded fallback; no uncited model answer. |

Also assert that retrieval is capped, source metadata reaches response generation, prompts and
responses remain bounded, and the information path does not call weather, fire-ban, geocoding, or
SMS-send code during unit tests.

## Implementation boundary

- Configure the single Bedrock Knowledge Base using the MVP settings above and load the existing file
  once.
- Add a small local retrieval adapter so handler tests do not construct AWS clients or make live
  calls.
- Add the offline evaluation and contract tests above.
- Any live retrieval check is explicit, opt-in, redacted, and separate from unit tests.

No scheduled ingestion, source polling, corpus refresh, park-page scraping, automatic data update,
or freshness enforcement for time-sensitive park information is implemented by this stage. The
one-time corpus and any retrieved hours or rental details must not be presented as continuously
current.

## Implementation record

- The typed local adapter and Bedrock `Retrieve` adapter cap results at three, use bounded network
  timeouts, preserve only safe citation metadata, and do not log raw retrieval payloads. The checked-in
  `.metadata.json` sidecar supplies corpus-level source metadata; live Bedrock source-URI and custom
  park/section/claim metadata are parsed without retaining unknown fields.
- The handler uses the existing interpretation call, then exactly one retrieval and one bounded
  response-generation call for `information_lookup`. Current openings, closures, reservations,
  and availability redirect before either call; weather and fire-status retain their existing paths.
- CDK configures a versioned corpus object plus metadata sidecar, S3 Vectors bucket/index, Titan Text
  Embeddings V2, and fixed 300-token chunks with 10% (30-token) overlap. Stack outputs record the
  generated IDs, region, corpus URI, and source SHA-256. The required ingestion job is intentionally
  a post-deploy manual step; see `docs/performance.md`.
- A response is sent only when it has usable source metadata and passes conservative grounding and
  current-status checks. Structured contradictory claims for the same park and section return the
  deterministic uncertainty fallback rather than model prose.

## Acceptance criteria and non-goals

- A user can ask a supported park-information question and receive a concise answer grounded in the
  one-time corpus.
- The response includes source attribution or a clear source label.
- Unsupported current-status questions are redirected to Stage 9.2, weather, reservations, or the
  appropriate live source.
- Missing retrieval evidence produces a bounded uncertainty response rather than a guess.
- The corpus and retrieval configuration are versioned and auditable.
- No live SMS acceptance check or automated ingestion is authorized by this spec. One-time AWS setup
  and an explicit redacted retrieval smoke test are allowed only as separately requested live checks.
