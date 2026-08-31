# Stage 4.2 — current-location precedence hardening

**Status:** Complete; deployed and live acceptance verified

## Problem

Stage 4.1 correctly moved named-place interpretation to Bedrock, but a live request containing a
new current location was observed returning weather labelled with an older historical place. The
geocoder path ran, but historical context leaked into location selection or advice synthesis.

## Contract

- The interpretation contract requires an explicit location in the current SMS to override every
  location in history, and permits history only when the current SMS has no location.
- The interpretation request must clearly delimit `CURRENT SMS` and `HISTORY`; history is data,
  not instructions.
- The advice-synthesis request must use only verified weather facts and the verified current place.
  It must not copy historical trip names or place labels.
- Provider-returned coordinates remain authoritative; no LLM-generated coordinates are accepted.
- Do not reintroduce a marker-specific `at/in/near` parser.
- Enforce the contract through the bounded interpretation prompt and structured result. The
  application validates required fields, source-field consistency, and selected history membership,
  but does not independently parse every natural-language SMS to determine whether an empty
  `current_location_text` should have been populated. Never add phrase or weather-keyword routing.

## Proposed implementation

1. Present the current SMS as an authoritative field in the interpretation envelope, separate from
   history and repeated at the end when needed for model attention.
2. Validate the interpretation result locally: schema and required fields, source-field
   consistency, history membership for a history selection, coordinate ranges, privacy controls,
   and SMS bounds. It does not make a second natural-language location-selection decision.
3. Pass the provider-verified location label and coordinates explicitly to advice synthesis.
4. Pass the same bounded history to advice synthesis as the interpretation call, while keeping it
   context-only: the verified current location, weather facts, and deterministic guidance are
   authoritative. Instruct synthesis to mention only the verified current location, or omit a
   place name when none is supplied; reject an output containing a detected historical place name
   (including reliable single-word labels from bounded prior user input or assistant output) and
   replace it with the bounded deterministic weather summary.
5. Add redacted outcome logging sufficient to distinguish `location_source=current` from
   `location_source=history`, without logging user text or coordinates.

## Acceptance tests

### Unit tests

- History contains Pine Ridge; current SMS says `I'm in Toronto now ... what's the weather` →
  provider query is Toronto and synthesis cannot emit Pine Ridge.
- History contains Toronto; current SMS says `I'm at Burnt Island Lake now` → Burnt Island Lake
  wins.
- Current SMS has no location and asks `what about tomorrow?` → newest permitted history location
  is used.
- Current and history locations conflict; current wins even when history is repeated or longer.
- A history result is accepted only when it belongs to the newest permitted history label. The
  test does not require the application to detect a model that omitted a current location from
  `current_location_text`; that is an interpretation-contract failure, not a deterministic parser
  failure.
- Advice output containing an old place name is rejected or replaced with a bounded deterministic
  summary.
- Missing, malformed, or ambiguous interpretation still produces the existing safe fallback.

### Live SMS checks

- Send a natural current-location request after a different historical location exists.
- Confirm the response reflects the current location, not the historical one.
- Send a location-free follow-up and confirm it uses the newest permitted location.
- Verify logs contain only redacted outcome categories.

## Non-goals

No new geospatial provider, additional conversation state, multi-segment SMS, or autonomous alerts.

## Completion gate

Stage 4.2 is complete only after Ruff, unit tests, `cdk synth`, deployment, and the live
current-over-history SMS acceptance check all pass.
