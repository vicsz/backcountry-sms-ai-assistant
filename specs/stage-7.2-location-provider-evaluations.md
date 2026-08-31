# Stage 7.2 — location-provider evaluations

**Status:** Complete; offline and provider-live evaluations passing

## Goal

Create an independent evaluation suite for named-place lookup and candidate ranking. It must test
the actual approved provider APIs with public queries and verify that the selected candidate is the
correct place before weather or Bedrock synthesis is involved.

## Scope

Use versioned fixtures containing a scenario ID, query, expected provider behavior, acceptable
candidate names, expected country/region, coordinate tolerance, expected source where stable, and
whether ambiguity or nonexistence is expected.

The suite must include at least Burnt Island Lake, Algonquin; Portage Store; Algonquin Park;
Toronto; NYC or New York City; an ambiguous place such as Springfield; a nonexistent place; and
provider timeout, malformed response, and unavailable-provider cases.

The provider suite receives a plain place query. It does not call Bedrock, weather, DynamoDB, or
SMS.

## Execution modes

### Offline (default)

Use deterministic provider responses to test normalization, provider ordering, country/region
bias, candidate filtering, acronym matching such as NYC to New York City, confidence thresholds,
distance checks, ambiguity handling, and failure mapping. Offline runs must make no network calls.

### Provider-live (opt-in)

Call the configured geocoding and Places APIs with public queries and short timeouts. Record the
provider, region/configuration, query, candidate count, selected candidate, coordinates, latency,
and outcome. No Bedrock call or SMS is permitted.

Live results must be validated against explicit tolerances and acceptable names, not exact raw API
payloads. Provider data can change; a changed result must be reported as evidence requiring review,
not silently accepted.

## Deterministic assertions

For resolved scenarios, assert a candidate was returned, its canonical or acceptable name, expected
country and region where available, coordinates within the fixture tolerance, expected provider
source where stable, and that no unrelated distant candidate was selected.

For ambiguity and failure scenarios, assert the correct non-resolved outcome and that no coordinate
is passed onward. Provider-returned coordinates remain authoritative; this suite must not invent or
repair coordinates.

## Runner and acceptance

Provide one explicit mode-selecting command, for example:

```text
pytest -m eval_location --eval-mode=offline
pytest -m eval_location --eval-mode=provider-live
```

Acceptance requires offline coverage for all provider outcomes and a bounded provider-live matrix
covering Burnt Island Lake, Portage Store, Toronto, NYC, ambiguity, and nonexistence. Live tests
must never be part of ordinary pull-request validation unless explicitly enabled.

## Non-goals

No Bedrock interpretation, weather fetching, SMS sending, provider replacement, hardcoded place
catalog, or automatic acceptance of changed provider data.
