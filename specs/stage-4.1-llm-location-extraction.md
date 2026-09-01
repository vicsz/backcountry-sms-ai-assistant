# Stage 4.1 — LLM-driven location extraction

**Status:** Complete; deployed and live acceptance verified. BUG-0001 follow-up correction is
verified on the dedicated capture stack; production rollout remains pending.

## Goal

Replace brittle phrase-based named-location parsing and keyword-based weather routing with a
bounded Bedrock interpretation call. The LLM interprets natural SMS wording and classifies intent;
geospatial providers remain authoritative for resolving a place to coordinates. This is an
incremental refinement of Stage 4, not a replacement of the deployed GPS and named-place weather
flow.

## Request contract

- Every weather request must contain a location in the current SMS or an explicitly supported
  history context.
- The interpretation call receives the current SMS and the bounded conversation history.
- It returns structured JSON only, with exactly these seven keys and no extras:

```json
{
  "intent": "weather",
  "location_text": "Toronto",
  "current_location_text": "Toronto",
  "coordinates": null,
  "time_window": "now",
  "activity": "general",
  "location_source": "current"
}
```

- `intent` is one of `weather`, `general`, or `unclear`.
- `location_text` is the place phrase as understood from the message, cleaned of conversational
  or temporal filler such as `now`, `currently`, `this evening`, `tonight`, and `please`.
- `current_location_text` is the cleaned place phrase from the current SMS only, or an empty
  string when no current location is extracted. When it is non-empty, it must match `location_text`
  and `location_source` must be `current`.
- `current_location_text` is mandatory in every valid interpretation. `null`, omission, or a
  non-string value is malformed and is rejected before geocoding. When the model returns an empty
  string for this redundant field but returns a current-sourced `location_text` whose exact bounded
  phrase is present in CURRENT SMS, the application may canonicalize `current_location_text` from
  that grounded field.
- A request such as `Weather in Collingwood this evening` must produce `Collingwood` for both
  named-location fields and `evening` as the time window. The place is unqualified by country or
  province, so the interpretation and provider path use Canada as the country prior and prefer
  Ontario without inventing coordinates or turning the missing-place case into Collingwood.
- Current/history precedence is owned by the bounded interpretation contract. The application
  validates its structured invariants—required fields, a matching current-source pair, and history
  membership—but does not independently parse the natural-language current SMS to decide whether
  the model should have selected history. Do not add marker-specific parsers for phrases such as
  `at`, `in`, or `near`; a location-free follow-up may still use the newest permitted history
  location.
- A current-sourced named place is rejected unless `current_location_text` is present and matches
  `location_text`. Direct current-SMS coordinates remain separately validated and do not require a
  named location.
- Any non-coordinate `location_text` must have either the validated `current` source or a
  legitimate location-free `history` follow-up source; a non-empty location with source `none`
  is rejected before geocoding.
- A history-sourced named location must match the newest available proper-name location label in
  supplied history, considering both bounded prior user input and assistant output. Otherwise it
  is treated as an unsourced model value and rejected before geocoding.
- `coordinates` is either `null` or exactly `{ "latitude": number, "longitude": number }`, with
  real `int`/`float` values (never booleans or numeric strings). The model may normalize syntax but
  may not invent, move, or silently substitute a point.
- The application validates coordinate object keys, value types, ranges, and conflicts before any
  provider use.
- If the request has no usable location, reply with a concise request for GPS coordinates or a
  named place.

## Proposed flow

1. Receive an allow-listed SMS.
2. Call Bedrock once for every message to classify intent and extract location, coordinates, time
   window, and activity from the current SMS plus bounded history.
3. If `intent` is `weather`, resolve the location and fetch weather, then call Bedrock a second
   time for concise advice.
4. If `intent` is `general`, call Bedrock a second time for the normal assistant response.
5. If `intent` is `unclear`, call Bedrock a second time for a concise clarification.
6. If valid coordinates are returned, use them directly; do not geocode them.
7. Otherwise, submit `location_text` to the approved geospatial providers.
8. Accept only a provider-returned candidate that passes existing confidence and geography checks;
   never use the LLM to create coordinates.
9. Fetch weather for the verified coordinates.
10. Apply deterministic camping/paddling guidance.
11. Normalize output to GSM-7 and one SMS segment (160 septets), then send it.

Every valid interpretation therefore uses exactly two LLM calls: interpretation followed by a
bounded response. This includes weather requests that need a location prompt, invalid coordinates,
unresolved named locations, and provider/weather failures. Malformed or failed interpretation has
no valid first result and uses one deterministic fallback instead. The weather path has provider
calls between those two LLM calls when a location can be resolved.

## Interpretation prompt requirements

The fixed system prompt must require:

- JSON-only output matching the schema;
- intent classification for every message, including non-weather messages;
- no invented locations, coordinates, weather, or certainty;
- conversational filler removal;
- a current whereabouts statement supplies the weather location even when the weather question
  follows separately (for example, `I'm in Toronto now, what's the weather?`);
- preference for the most recent explicit location in supplied history;
- current-message location taking precedence over history;
- `current_location_text` only when it is grounded in the current SMS, and never conflicting with
  `location_text` or `location_source`; this is an LLM instruction, not a local natural-language
  parser requirement;
- `null` or an empty field when location is absent or unclear;
- bounded short strings and no sensitive data.

The implementation must tolerate fenced or prefixed JSON only through a bounded parser and must
fall back safely when the response is malformed.

## Edge-case test matrix

### Unit tests (always run)

- `I'm in Toronto now ... what's the weather` → `Toronto`, not `Toronto now`, even though the
  location is expressed as where the user is rather than as `weather in Toronto`.
- `Currently near the Portage Store, forecast tomorrow?` → `Portage Store`.
- `Weather in Collingwood this evening` → `Collingwood` and `evening`; no extraction rejection.
- `weather at 45.62 N, 78.42 W` → exact normalized coordinates; no geocoding call.
- Decimal, compass, labelled, slash-separated, and extra-whitespace coordinate formats.
- Latitude/longitude outside valid ranges → correction reply; no weather call.
- A location containing punctuation or filler (`Toronto, Ontario please`).
- Missing location (`what's the weather?`) → location-request reply.
- Ambiguous location (`Springfield weather`) → clarification reply, never a guess.
- Non-weather message → `general` intent and a second Bedrock response call.
- Ambiguous request → `unclear` intent and a concise clarification response.
- Current location overrides a different location in history.
- Follow-up uses the newest location in history when the current message omits one.
- A structurally valid history selection is checked against permitted history membership; the
  application does not attempt to infer a missed current location from free-form SMS text.
- LLM returns `null`, empty, fenced, prefixed, malformed, or extra JSON fields; an extra field is
  rejected before geocoding.
- LLM returns a plausible but invented coordinate for a named place → reject it.
- Geocoder returns no candidates, conflicting candidates, or a distant candidate.
- Bedrock timeout, throttling, access denial, and provider timeout.
- Long, Unicode, emoji, and GSM-7 extended output remains one SMS segment.
- Prompts and logs contain no phone numbers, secrets, raw provider payloads, or precise user-linked
  coordinates.

### Opt-in live integration tests

Run explicitly with:

```bash
RUN_LIVE_INTEGRATION=1 AWS_PROFILE=backcountry-dev pytest -m integration
```

Use public, non-user-specific inputs and short timeouts. The matrix should include Toronto wording,
GPS coordinates, Burnt Island Lake, Portage Store, a missing location, and an ambiguous place.
Assertions should validate the JSON contract, provider resolution, exact coordinate preservation,
safe fallbacks, and bounded output—not exact generated prose.

### SMS acceptance checks

- Natural wording with a city resolves successfully.
- Natural wording with an outdoor POI resolves successfully.
- GPS input still uses the exact supplied point.
- Missing and ambiguous locations ask for clarification.
- A follow-up with no new location uses the newest permitted context.

## Failure behavior

- Interpretation failure or malformed JSON → deterministic fallback or location-request reply.
- Invalid coordinates → correction reply.
- No or ambiguous provider result → concise clarification.
- Provider failure → fixed location-unavailable reply.
- Weather failure → fixed weather-unavailable reply.
- Synthesis failure → bounded deterministic weather summary where safe.

## Non-goals

No new provider, location cache, conversation-history redesign, managed Guardrails, autonomous
alerts, route recommendations, or multi-segment SMS.

## Acceptance criteria

- Conversational location wording resolves without marker-specific parsing rules.
- Weather routing is LLM-based; no weather keyword allow-list is required.
- Coordinates remain exact and provider-backed.
- Existing Stage 3/4 behavior and two-call weather flow remain intact.
- Unit and opt-in integration tests cover the edge-case matrix.
- Ruff, the full unit suite, and `cdk synth` pass before deployment.
