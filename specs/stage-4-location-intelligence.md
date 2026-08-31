# Stage 4 — location intelligence

**Status:** Complete; deployed and live acceptance verified

## Goal

Extend the deployed GPS weather MVP so each request can use either cleaned GPS coordinates or a
provider-resolved named outdoor place, while preserving the existing weather, safety, logging, and
one-segment SMS controls.

## Request contract

- Every weather request includes its location in the same SMS.
- GPS coordinates are authoritative. The LLM may normalize labels, separators, and compass
  notation, but must not invent, move, or silently substitute coordinates.
- Named places are resolved through provider-backed search; do not maintain a hardcoded alias or
  lake catalog in application code.
- When a named request omits a country or region, rank Canada, Ontario, and outdoor/backcountry
  candidates first, but do not exclude valid locations elsewhere. This is a ranking hint, not
  permission to guess.
- A provider result supplies the coordinates. The LLM may extract the place phrase and rank returned
  candidates, but may not create coordinates itself.
- Low-confidence, distant, ambiguous, or conflicting results require clarification or GPS input.
- No conversation history or remembered location is used.

Examples:

- `Weather at 45.62 N, 78.42 W tomorrow morning`
- `Weather at Burnt Island Lake, Algonquin tomorrow`
- `Will I need a tarp at Portage Store tonight?`

## Proposed flow

1. Receive an allow-listed SMS.
2. Use a bounded Bedrock extraction call to identify intent, location text, activity, and time
   window.
3. If coordinates are present, normalize and validate them without geocoding.
4. Otherwise, query approved geospatial providers and collect candidate names, coordinates,
   feature types, and regions.
5. Rank candidates using provider metadata and the request context. Apply confidence, distance,
   region, and feature-type checks; clarify instead of guessing.
6. Fetch structured weather for the verified coordinates.
7. Apply deterministic paddling and camping rules.
8. Use one bounded Bedrock synthesis call to phrase practical advice from verified facts only.
9. Enforce GSM-7-safe output and one SMS segment.
10. Send the reply.

## Provider strategy

Provider selection must pass the preflight gate before implementation. Candidate sources include:

- NRCan Canadian GeoNames for official geographic names and waterbodies.
- Ontario geographic-name or open-data services for Ontario-specific features.
- Amazon Location Places for businesses, access points, outfitters, and general points of interest
  in Canada and the United States.
- OpenStreetMap services only as a rate-limited fallback where licensing and usage limits permit.

The resolver may query more than one source, but must retain the source and confidence internally.
It must reject a plausible-sounding but geographically wrong match.

## LLM responsibilities

The extraction call may clean coordinate syntax and produce a normalized place query. A separate
bounded ranking call may select among returned candidates. Neither call may invent a location,
weather fact, alert, or certainty. The synthesis call receives only verified location metadata,
weather fields, and deterministic rule results.

## Integration-test contract

### Default tests

Unit tests mock all external services and run on every change. They cover coordinate cleanup,
provider routing, candidate ranking, ambiguity handling, prompt contracts, fallbacks, and SMS
length/encoding.

### Opt-in live tests

Live tests are isolated under `tests/integration/` and require explicit opt-in:

```bash
RUN_LIVE_INTEGRATION=1 AWS_PROFILE=backcountry-dev pytest -m integration
```

They may call the real geocoding providers, Open-Meteo, and Bedrock. Use short timeouts, bounded
requests, rate limits, redacted logs, and public static test inputs. Do not run them in ordinary PR
validation unless explicitly configured.

The live matrix should include known coordinates, Burnt Island Lake, Portage Store, Algonquin
Park, a common abbreviated U.S. city such as NYC, an ambiguous name, and a nonexistent name.
Bedrock tests assert schema and safety contracts,
not exact prose.

## Pre-implementation gate

Before adding providers, dependencies, IAM permissions, or Lambda code:

1. Verify each API from the local environment.
2. Verify required fields, coordinate order, licensing, and rate limits.
3. Verify Lambda network reachability and timeout behavior.
4. Verify Bedrock extraction/ranking calls with the selected model.
5. Add unit and opt-in integration tests before deployment.

## Failure behavior

- Invalid coordinates → request corrected coordinates.
- No named-place candidates → request GPS or more context.
- Ambiguous/low-confidence candidates → ask a concise clarification question.
- Provider failure → fixed location-unavailable reply.
- Bedrock failure → deterministic extraction/synthesis fallback.
- Weather failure → fixed weather-unavailable reply.
- Any output over one segment → bounded replacement or truncation.

## Logging and privacy

Log only redacted outcome codes such as `coordinate_normalized`, `location_candidates_found`,
`location_ambiguous`, `location_resolved`, and provider failure categories. Never log phone
numbers, message bodies, prompts, model output, secrets, raw provider payloads, or precise
coordinates tied to a person.

## Explicit non-goals

No conversation memory, route or portage recommendations, autonomous alerts, emergency dispatch,
DynamoDB tracking, managed Guardrails, multi-recipient messaging, or multi-segment SMS.

## Acceptance criteria

- Existing coordinate requests continue to work unchanged.
- Common coordinate formats normalize to the exact intended point.
- Named places resolve only from provider candidates and pass confidence checks.
- Wrong, ambiguous, and missing locations produce clarification rather than guessed weather.
- Real provider and Bedrock integration tests are opt-in and redacted.
- Final advice remains conservative, useful for camping/paddling, and one SMS segment.
