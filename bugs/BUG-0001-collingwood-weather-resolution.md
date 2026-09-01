# BUG-0001 — Collingwood weather request was rejected

## Status

Awaiting Live Verification

## Reported behavior

On 2026-09-01, a user-provided Messages screenshot showed the assistant rejecting a weather
request for Collingwood, Ontario and asking for GPS coordinates or a named place. The request
already contained a named place.

## Expected behavior

A weather request containing an unqualified named place should be interpreted as a named-place
request, then resolved through the approved provider path. Unqualified place resolution should use
Canada as the country default and prefer Ontario when no other region is given, while retaining
provider authority and relevance/popularity ranking.

## Reproduction and evidence

- Reproduction input: User-provided Messages screenshot showing a named Collingwood weather request.
- Reproduction result: The assistant returned the weather-extraction/location clarification instead
  of attempting named-place resolution.
- Evidence location: Original screenshot attached in the conversation; it was not copied into the
  repository because raw message content is not permitted in committed fixtures or bug records.

The screenshot establishes the externally observed failure and the returned fallback. The first
post-fix deployed capture later established the specific failure category
`weather_extraction_ungrounded_current_location`; the model output itself is not retained because
raw model responses are excluded from logs and committed evidence.

## Impact

Natural-language weather requests for a common Ontario place could fail before the location provider
was called, causing an unnecessary GPS clarification and preventing a weather response.

## Analysis and root cause

The handler requires Bedrock interpretation to produce a valid named location before it reaches
provider-backed geocoding. The observed reply matches the weather-extraction fallback, so the failure
occurred at or before interpretation validation rather than in weather retrieval. The exact model
failure mode is not observable from the screenshot alone; confidence is high for the failing boundary
and medium for the underlying model output.

The interpretation prompt did not sufficiently constrain temporal wording in the named-location
fields for a request such as Collingwood plus an evening qualifier. The deployed Nova Micro capture
returned a location representation that failed the handler's strict current-location grounding
check, so the request stopped before provider lookup. The provider ranking also did not explicitly
score Canada as a regional preference when Amazon Places returned competing same-name candidates.

The direct synthetic Bedrock check later isolated the representation: `intent` was `weather`,
`location_text` was `Collingwood`, `time_window` was `evening`, and `location_source` was `current`,
but the redundant `current_location_text` was empty. The exact model response is not retained.

## Fix

Commit `5ba8fa3` (`Improve Ontario named-place resolution`) made the smallest scoped correction:

- clarified the interpretation prompt to assume Canada and prefer Ontario for unqualified named
  places, using Collingwood as an example without hardcoding it as a default location, and explicitly
  separated temporal wording from the place fields;
- canonicalized an omitted redundant current-location field when the model's current-sourced place
  is explicitly present in the current SMS;
- added Canada and Ontario preference to provider candidate ranking while preserving provider-returned
  coordinates and relevance scores as authoritative;
- added Collingwood path and competing-candidate regression coverage.

Non-goals: no hardcoded Collingwood coordinates, no default location when the user provides no place,
no automatic acceptance of model-invented coordinates, and no real SMS delivery.

## Regression tests

- `test_collingwood_named_location_reaches_provider_backed_weather_path` verifies that a valid
  Collingwood interpretation reaches named-place resolution and weather synthesis.
- `test_unqualified_common_place_prefers_ontario_candidate` verifies that an Ontario Collingwood
  candidate outranks a same-name U.S. candidate even when the U.S. provider score is higher.
- `test_interpreter_prompt_sets_canada_ontario_named_place_defaults` protects the interpretation
  contract wording.
- `test_current_grounded_location_can_fill_omitted_redundant_field` protects the deployed model
  behavior that originally caused this bug.

The first deployed capture after commit `5ba8fa3` failed with the redacted outcome
`weather_extraction_ungrounded_current_location`, so the fix remains subject to a second deployment
and live capture after the prompt correction.

The corrected implementation was deployed to the dedicated `BackcountrySmsEchoTest` capture stack
and verified with synthetic run `BUG-0001-live-collingwood-003`. The run resolved the place through
NRCan, completed the weather path, returned a bounded weather response, and reported
`sms_api_called=false` and `sns_published=false`.

## Validation results

- Ruff: passed.
- Full unit suite at fix completion: 162 passed, 19 skipped.
- CDK synthesis: passed using the project virtualenv app command.
- `git diff --check`: passed.
- Commit was pushed to `origin/main`.

## Deployment/live-verification status

Required because the observed defect involved deployed Bedrock interpretation and provider-backed
weather behavior. Dedicated test-stack live verification passed, but the production stack was not
changed or invoked because it uses live SMS delivery. Keep this record in `Awaiting Live Verification`
until the production rollout and its separately authorized verification are complete.

## Fixing commit

`d951ff1 BUG-0001 -- harden Collingwood weather resolution` (supersedes the initial partial fix in
`5ba8fa3`).
