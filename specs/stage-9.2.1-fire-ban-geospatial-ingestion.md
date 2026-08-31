# Stage 9.2.1 — Fire-ban and geospatial-source ingestion extension

Status: Proposed; blocked on completion and evidence from Stage 9.2

## Objective

Automate the refresh and validation of the static fire-ban/geospatial lookup introduced by
`specs/stage-9.2-fire-ban-geospatial-lookup.md`, while preserving source authority, versioned
snapshots, last-known-good data, and explicit uncertainty.

## In-scope extensions

- Retrieve the Ontario Parks alerts source and the official LIO park geometry source on a bounded
  schedule and on an explicit/manual refresh request.
- Detect source changes, retain raw artifacts, calculate source hashes, and promote only validated,
  complete snapshots.
- Validate schema, required identifiers, geometry validity, coordinate reference system, duplicate
  parks/alerts, timestamps, and join coverage before promotion.
- Preserve the last known good snapshot when retrieval, parsing, validation, or promotion fails.
- Emit refresh outcome, source version, record counts, validation failures, snapshot age, and last
  successful refresh without logging personal data or secrets.
- Add the Ontario Restricted Fire Zone source as a separately authoritative provincial restriction
  layer and define deterministic conflict handling with Ontario Parks alerts.
- Investigate broader source coverage in a separate discovery record before adding municipal,
  conservation-authority, Indigenous-government, Parks Canada, or other jurisdictions.
- Expand from fire bans to relevant park closures only after status semantics, geography, and source
  authority are defined per source.

## Refresh and failure contract

- Refreshes are idempotent and produce immutable snapshot identifiers.
- A partial or malformed refresh is never visible as the current snapshot.
- Stale data must be surfaced to the handler as `unknown` or explicitly stale, with the last
  successful refresh time.
- Source wording is preserved; normalization may classify but may not invent legal meaning.
- The scheduled path must not be hidden in unit tests and must not send SMS.

## Evaluation and acceptance criteria

- Repeated refreshes of unchanged sources produce equivalent normalized content and a traceable
  snapshot outcome.
- Changed, missing, malformed, conflicting, stale, and partially unavailable sources are covered by
  offline fixtures.
- A live source/provider check is opt-in, separately gated, redacted, and excluded from unit tests.
- The runbook documents refresh cadence, manual retry, rollback to the last good snapshot, stale
  behavior, cost, Athena latency, and operator evidence.
- Broader jurisdiction coverage is not declared complete until each source's authority, coverage,
  terms, update behavior, geometry model, and status semantics are verified.

No implementation or deployment is authorized by this extension until Stage 9.2 has established
the initial source and query contract.
