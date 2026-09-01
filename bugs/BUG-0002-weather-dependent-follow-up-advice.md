# BUG-0002 — Weather-dependent follow-up advice is rejected

## Status

Closed

## Reported behavior

After the user established that they were at Burnt Island Lake and received a weather response for
tomorrow, the assistant rejected these follow-ups:

- `Can I safely cross this lake at noon?`
- `Should I put the tarp up before bed?`

The assistant asked for GPS coordinates or a named place even though the recent conversation already
contained the grounded location.

The later deployed-demo check also exposed two related failures in this same behavior contract:
`We're planning a long crossing tomorrow morning. What should we watch for?` was routed to the
Ontario Parks guide instead of weather, and the preceding weather response said `Safe for paddling`.

## Expected behavior

When recent conversation history contains a grounded location, a follow-up outdoor decision question
should use that location when current weather would materially help answer it. The assistant should
retrieve the relevant forecast window and provide concise, conditional weather-based guidance. It must
not claim that a crossing or camping setup is definitively safe, and it must not invent unsupported
park, route, campsite, or current-condition facts.

## Reproduction and evidence

- Reproduction input: User-provided Messages screenshot showing the Burnt Island Lake conversation and
  the two rejected follow-up questions.
- Reproduction result: The assistant returned the location-request fallback for both weather-dependent
  questions.
- Evidence location: Original screenshot attached in the conversation; it is not copied into the
  repository because raw message content is not permitted in committed fixtures or bug records.

The earlier `Tomorrow?` follow-up received a weather response, so location retention is unlikely to
be the primary failure. Initial code inspection identified two likely boundaries: the extraction
prompt does not clearly classify weather-dependent decision questions without explicit weather
keywords, and hourly selection does not currently identify `noon` or `midday` as a target hour.

## Impact

Users cannot ask practical trip-planning questions that depend on weather while continuing a valid
conversation, even when the assistant already has a grounded location and can retrieve a forecast.

## Analysis and root cause

Reproduction confirmed that recent history was available and worked for `Tomorrow?`, but the model
did not consistently classify weather-dependent decision questions as weather follow-ups. It also
varied between `location_source=none`, an ungrounded historical label, and a prior location mislabeled
as current. The handler consequently returned the location fallback even though the user had already
established Burnt Island Lake.

The extraction prompt lacked an explicit semantic rule for outdoor decisions and deictic references
such as `this lake`, `here`, and `the campsite`. The handler also lacked a safe normalization path for
model labels that referred to a grounded history location with an added qualifier or current-source
mislabel. Separately, `weather.select_weather_period` handled `tomorrow`, `morning`, and `tonight`,
but not `noon` or `midday`, so a successful crossing interpretation could select the wrong hourly
period. Root cause confidence is high.

## Fix

Implemented locally:

- expanded the interpretation prompt to classify weather-dependent outdoor decisions as `weather`
  when forecast conditions would materially help, including location-free follow-ups that refer to a
  prior lake or campsite;
- expanded the advice prompt to use verified weather facts for conditional guidance without
  guaranteeing safety or inventing unsupported park, route, campsite, water-temperature, or current
  condition facts;
- canonicalized qualified and deictic history labels, corrected grounded history locations mislabeled
  as current, and discarded model coordinates not repeated in the current SMS;
- added `noon`, `midday`, and `mid day` hourly selection at 12:00.
- added deterministic routing for weather-dependent activity planning when the model classifies the
  question as guide information;
- rejected generated absolute safety claims such as `safe`, `safely`, `guaranteed`, and `no risk`
  in favor of the deterministic, conditional weather summary.

No activity-specific answer or location was hardcoded.

## Regression tests

- `tests/test_handler.py::test_bug_0002_prompt_routes_weather_dependent_outdoor_decisions` protects
  the semantic extraction and conditional-advice prompt contract.
- `tests/test_handler.py::test_bug_0002_history_location_with_qualifier_is_canonicalized` protects
  grounded history labels when the model adds a geographic qualifier.
- `tests/test_handler.py::test_bug_0002_deictic_history_location_uses_newest_grounded_label` protects
  `this lake`/`the lake` follow-ups when the model returns a deictic placeholder.
- `tests/test_handler.py::test_bug_0002_history_follow_up_discards_inherited_coordinates` protects
  the rule that coordinates are not carried from history into a new SMS.
- `tests/test_handler.py::test_bug_0002_model_current_label_is_downgraded_to_grounded_history`
  protects against the model labeling a prior location as current on a follow-up.
- `tests/test_weather_cache.py::test_noon_weather_window_selects_midday_period` protects selection
  of the requested midday forecast period.
- Model-eval cases `BUG-0002-CROSSING-001` and `BUG-0002-TARP-001` will cover history-grounded
  weather-dependent follow-ups when the Bedrock-live evaluation suite is run.
- `tests/test_handler.py::test_bug_0002_weather_dependent_crossing_bypasses_rag_after_misclassification`
  protects deterministic routing for planning questions.
- `tests/test_handler.py::test_bug_0002_rejects_absolute_safety_advice` protects bounded safety
  language.

## Validation results

- Focused BUG-0002 tests and guidance coverage: 10 passed.
- Ruff: passed.
- Full unit suite: 179 passed, 19 skipped.
- CDK synthesis: passed with the repository virtualenv app command.
- Demo live verification: passed on the redeployed dedicated capture stack. The synthetic crossing
  sequence reached the weather path and returned conditional wind/rain/visibility guidance without
  an absolute safety claim; `sms_api_called=false` and `sns_published=false`.

## Deployment/live-verification status

The defect involved Bedrock interpretation, weather-provider lookup, and deployed demo behavior. The
corrected implementation was deployed to the demo capture stack defined in `docs/environments.md`.
The synthetic location-and-crossing sequence was live-verified after redeployment; no SMS or SNS
delivery occurred. No production environment is deployed.

The earlier implementation passed an isolated demo check, but the later deployed-demo check exposed
the routing and advice gaps. The corrected implementation now passes the automated and demo checks.

The bug is closed because automated validation and demo-environment live verification are complete.

## Fixing commit

To be recorded after the change is committed.
