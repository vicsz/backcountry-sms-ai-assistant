# Stage 3 — location-aware paddling and camping assistant

**Status:** Implemented and deployed (GPS MVP)

## Goal

Extend the SMS assistant into a precise, location-aware weather and trip-planning assistant for
canoeing and camping.

## Request contract

- Every weather or trip-advice request must include a location in the same SMS.
- The first implementation accepts GPS coordinates. The LLM may clean up formatting, identify
  latitude versus longitude, and normalize a coordinate pair, but it must not change the location.
- Named lakes, parks, and trails are a planned follow-on. They must be resolved through a
  provider-backed geocoder or place-data source, not a hardcoded application catalog.
- Canada is the default country when a named-place request omits a country. Resolution should rank
  Canadian backcountry lakes, parks, and paddling areas above similarly named urban places when the
  request supplies that context (for example, `Burnt Island Lake` should naturally prefer the
  Algonquin location when the available place data supports that match).
- The LLM may normalize a place query and rank returned candidates using the user's wording, but a
  provider result and confidence threshold remain authoritative. It must never invent coordinates.
  Ambiguous or low-confidence results require clarification instead of guessing.
- Conversation history, remembered locations, and inferred locations from earlier messages are
  explicitly out of scope.
- A request with no location receives a short prompt asking for GPS coordinates (initially) or a
  named lake, park, region, or town once named-place resolution is implemented.

Examples:

- `Should we canoe early tomorrow at Burnt Island Lake, Algonquin?`
- `Will we need the tarp tonight at Burnt Island Lake, Algonquin?`
- `Weather at 45.62,-78.42 tomorrow morning?`

## Proposed flow

1. Receive an SMS.
2. Use one bounded extraction/normalization call to identify intent, coordinate text, activity, and
   time window. If a valid coordinate pair is already present, do not call a geocoder.
3. Validate the exact coordinate (or, in the later named-place phase, resolve it through a
   provider-backed geocoder and confidence check).
4. Fetch structured weather data for that exact coordinate.
5. Apply deterministic paddling and camping rules.
6. Generate concise, practical advice from the verified facts and rule results.
7. Validate the final response for safety, encoding, and SMS length.
8. Send one SMS segment.

## LLM responsibilities

### Request extraction and coordinate cleanup

The extraction call returns structured JSON only. For the initial coordinate-first phase, it may
remove labels such as `lat`/`lon`, normalize separators, and validate coordinate ranges. It must not
answer the user, infer a missing coordinate, or silently substitute a nearby place.

### Later named-place resolution

Named-place support is intentionally separate from the coordinate-first MVP. A later resolver may
use a geocoder/place-data API plus LLM ranking to handle requests such as `Burnt Island Lake,
Algonquin`. The LLM can use Canada as the default and backcountry/paddling context as ranking hints,
but only a verified provider candidate can supply coordinates. The resolver must return the selected
place name, coordinates, source, and confidence for downstream logging and safety checks.

### Advice synthesis

The advice call receives only resolved coordinates, weather facts, alerts, and deterministic rule
results. It may phrase the advice, but must not invent weather facts, warnings, locations, or
certainty.

Explicit joke requests remain supported through the simple one-call Bedrock path, but jokes are no
longer the primary assistant behavior.

## Weather data

Recommended initial provider: Open-Meteo.

- No registration or API key for the intended non-commercial demo use.
- Coordinate-based forecast with hourly precipitation, probability, wind, gusts, and temperature.
- Confirm current terms, rate limits, attribution, and selected fields before implementation.
- Canada’s official MSC GeoMet API remains a possible alternative if official Canadian data is
  prioritized over the simplest integration.

The initial weather call is coordinate-only. Geocoding and named-place lookup must pass their own
API preflight before being added.

## Pre-implementation API gate

Before changing Lambda code, CDK, permissions, or dependencies:

1. Verify the proposed API works from the local environment.
2. Verify its response contains every required field.
3. Verify the Lambda runtime can reach it.
4. Confirm rate limits, attribution, and licensing.
5. Only then implement the adapter and infrastructure changes.

## Deterministic trip guidance

Rules may derive rain timing, wind and gust risk, lightning or severe-weather warnings, temperature,
overnight conditions, and conservative canoeing or tarp recommendations. The system must distinguish
forecast facts from recommendations and use conservative wording when conditions are uncertain.

## SMS constraints

- Final response must fit one SMS segment.
- Target approximately 140 GSM-7 characters.
- Avoid emojis and Unicode punctuation where possible; Unicode can reduce the segment limit.
- Normalize curly quotes, em dashes, and unsupported symbols.
- Calculate actual GSM-7/Unicode segment size.
- Truncate or replace output if necessary.
- Never silently send multiple segments.

## Failure behavior

- Missing location → request a location.
- Ambiguous location → request clarification.
- Weather provider failure → fixed weather-unavailable reply.
- Extraction failure → fixed request-understanding reply.
- Advice-generation failure → deterministic short weather summary.
- Unsafe or unsupported advice → conservative fallback.
- Raw provider forecast timestamps are internal selection data and must not appear in the user-facing
  SMS; use natural time-window wording such as `tonight` or `tomorrow` when appropriate.
- Unapproved sender → no provider, LLM, or SMS call.

## Logging

Log only redacted outcome codes such as `weather_request_parsed`, `location_resolved`,
`location_ambiguous`, `weather_provider_failed`, and `sms_output_bounded`.

Never log phone numbers, message bodies, precise coordinates tied to a person, raw weather payloads,
prompts, or model output.

## Explicit non-goals

No conversation memory, multi-day expedition planning, route or portage recommendations, emergency
dispatch, autonomous alerts, DynamoDB, managed Bedrock Guardrails, multi-recipient messaging, or
automatic multi-segment SMS.

## Acceptance criteria

- A weather request with a valid coordinate uses that exact location after LLM formatting cleanup.
- The coordinate-first path does not call a geocoder or infer a location.
- A later named-place path uses provider-backed resolution, defaults country to Canada, prefers
  backcountry/paddling candidates when supported by the returned data, and never relies on a
  hardcoded lake catalog.
- A request without a location does not call the weather provider or reuse prior context.
- Ambiguous locations produce clarification rather than a guessed forecast.
- Weather facts and deterministic rules are passed to advice synthesis without raw provider prose.
- Provider timeout/error and LLM failures produce safe bounded fallbacks.
- Final output is one valid SMS segment with no unsupported Unicode where avoidable.
- No raw user data or provider payload appears in logs.
