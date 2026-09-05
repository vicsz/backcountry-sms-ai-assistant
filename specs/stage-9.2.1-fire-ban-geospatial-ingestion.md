# Stage 9.2.1 — Live-verifiable fire-ban and geospatial ingestion

Status: Deferred implementation; specification complete. Stage 9.2's prepared local snapshot
remains the current implementation; live source retrieval, S3 publication, Athena query,
deployment, and provider verification are not yet implemented or established by this document.

## Discovery-only source reachability check — 2026-09-05

A bounded, read-only fetch confirmed that the three documented official endpoints responded without
writing or promoting data. The check retained only redacted size/hash metadata: Ontario Parks
alerts returned 182,436 bytes (`sha256:c56acc03010f3be67a9a259468c8db6a85b2bbe51cf7b28a9b625d627c9ffe27`),
the LIO Provincial Park Regulated endpoint returned 10,119 bytes
(`sha256:8bafd98c5ac7949a32db71daf86d1077f9b2860e0439fa7541520a2a5501f90d`), and the LIO
Restricted Fire Zone endpoint returned 5,588 bytes
(`sha256:95edbc3abbe4179a271b24fbd7b4a5e35df423ccaa4439c0dc9763dfd7631617`). This proves
reachability at one point in time only. It does not establish terms approval, parser correctness,
coverage/join quality, a refresh schedule, a live feed, or a promoted snapshot.

## Objective

Define a bounded, repeatable ingestion path for the Stage 9.2 Ontario provincial-park lookup. A
promoted snapshot may be used by the deployed Demo handler only after source, provenance,
normalization, validation, publication, and live-verification gates pass. Source wording and
authority remain visible; absence never becomes permission to have a fire.

## Sources and authority

The parks-first MVP has two required source families:

1. Ontario Parks alerts: the primary park-level alert/status source, including park name, alert
   URL, alert type, exact wording, and the page's `as of` value.
2. Ontario LIO `Provincial Park Regulated`: the official provincial-park geometry and stable park
   identifier source used for point-in-polygon membership and the status join.

Reference sources:

- [Ontario Parks alerts](https://www.ontarioparks.ca/alerts)
- [Ontario LIO Provincial Park Regulated](https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open03/MapServer/4)
- [Ontario LIO Restricted Fire Zone](https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open08/MapServer/28)

The Ontario Restricted Fire Zone (RFZ) layer may be ingested as a separately labeled provincial
restriction layer only when its authority and coverage are verified. It must never be silently
merged with an Ontario Parks alert. Every source record and raw artifact must retain source name,
canonical URL, retrieval timestamp (UTC), source-provided timestamps, content hash, parser/schema
version, coverage statement, and a terms/availability check (robots/access rules, licence or open
data terms, rate limits, authentication, and whether automated retrieval is permitted). A source
that cannot be retrieved or whose terms do not permit the planned access is unavailable, not empty.

## Refresh and promotion pipeline

Refresh is scheduled at a bounded cadence and is also available as an explicit operator/manual
run. Each run must:

1. retrieve the bounded source resources and retain immutable raw artifacts;
2. record retrieval time, response metadata needed for audit, hashes, coverage, and terms check;
3. parse into the versioned normalized schema without inventing legal meaning;
4. validate identifiers, required fields, timestamps/time zones, supported status values, geometry
   validity/CRS/coordinate order, duplicate records, and park/status join coverage;
5. validate source freshness and cross-source consistency, producing a machine-readable report;
6. write an immutable `snapshot_id` containing the source hashes, schema/parser versions, and
   creation time; and
7. promote the snapshot atomically only if all required gates pass.

Partial, malformed, unbounded, or failed runs are never visible as current. Promotion must retain
the previous immutable last-known-good snapshot and a pointer to it. On first publication, there
is no current pointer until a complete snapshot passes every gate; the handler returns `unknown`
and no confirmed fire status is available. Rollback changes only the current pointer to that
snapshot and records operator, reason, time, and evidence. Unchanged input must produce equivalent
normalized content and a traceable no-change outcome.

Normalized records must include `source_name`, `source_url`, `source_record_id`, `source_hash`,
`jurisdiction`, `park_id`, `park_name`, `alert_type`, `normalized_status`, exact `raw_wording`,
`source_as_of`, `published_at` when available, `retrieved_at`, `effective_at` when available,
geometry and CRS metadata, `snapshot_id`, `snapshot_created_at`, and schema version.

## Deterministic status and failure semantics

The handler may return `fire_ban` only for an authoritative active fire-ban record in the
selected snapshot. A park with no Ontario Parks fire-ban row is reported only as “no Ontario Parks
fire-ban record in this snapshot,” with freshness and source context; it is never “no ban,”
“fires allowed,” or permission by implication. An RFZ result remains a separate restriction fact.

Return `unknown` (and preserve a reason and relevant timestamps) for stale or missing snapshots,
missing or invalid geometry, unresolved boundary points, no park match, conflicting sources,
unsupported status/geometry/CRS, source-down or terms-blocked retrieval, parse/validation failure,
Athena failure/timeout, or incomplete join coverage. A future-dated or otherwise impossible source
timestamp is invalid. Never substitute the nearest park, invent coordinates, infer current status
from absence, or let an LLM decide status, jurisdiction, geometry, or freshness. Fire lookup
failure remains independent of weather lookup.

Staleness thresholds must be configuration, documented with the snapshot, and evaluated against
UTC retrieval/source times. Stale data may support diagnostics only; it cannot support a confirmed
status. Geometry-boundary behavior must be deterministic: inside, outside, and boundary are
distinct outcomes, and an unresolved boundary is `unknown`.

## Deployed read path and safety boundary

The deployed Python handler reads only the atomically promoted `current` pointer and then queries
the referenced immutable snapshot. Snapshot ID, table/prefix, region, and freshness policy are
allow-listed, validated configuration; missing, malformed, or unexpected values fail closed to
`unknown`. The handler must not scrape sources, promote data, or scan a broad S3 prefix.

Athena access, if retained from Stage 9.2, must use a snapshot-pinned table/query, bounded
partitions and selected columns, explicit timeout/cancellation, and these initial hard limits:
each source response/page is at most 10 MiB, a refresh run produces at most 100 MiB of raw source
artifacts, a normalized snapshot contains at most 10,000 park records and 2,000,000 coordinate
vertices, and each handler query has a 5-second timeout and a 64 MiB scanned-bytes limit. The
publisher must retain raw artifacts for 90 days and the current plus five previous validated
snapshots for rollback, subject to documented lifecycle enforcement. The publisher role may write
only versioned artifacts, manifests, and the current pointer; the handler role is read-only and
may read only the current pointer and normalized snapshot data, never raw artifacts or any
publisher path. No unbounded Athena scan is permitted. Raw source payloads, message bodies,
prompts, model output, coordinates tied to people, credentials, and secrets must not appear in
logs or evidence.

## Verification and evidence

Implementation must provide, separately:

- offline unit tests and synthetic fixtures for valid, unchanged, changed, stale, missing,
  conflicting, unsupported, source-down, malformed, incomplete, invalid-geometry, boundary,
  outside-park, and no-status cases;
- parser contract tests against source-shaped fixtures, including provenance, hashes, coverage,
  terms metadata, and schema-version changes;
- an explicit opt-in live source/provider validation that records redacted retrieval times, hashes,
  coverage, terms result, parser/validation outcome, and no SMS side effect;
- deployed Demo capture-mode verification against `BackcountrySmsEchoTest`, proving the handler
  reads the promoted snapshot, applies freshness and safety semantics, and does not send SMS;
- operational checks for scheduled refresh, alerting, metrics, retry bounds, cost, Athena scan and
  latency limits, current-pointer integrity, last-known-good rollback, and recovery from source
  outage; and
- redacted, source-preserving evidence that distinguishes local fixtures, live source validation,
  promoted snapshot, deployed Demo behavior, and any separately authorized SMS check.

## Acceptance criteria

Pass requires all of the following; any failure leaves the prior last-known-good snapshot current:

- both required sources have documented authority, coverage, canonical retrieval method, terms/
  availability result, timestamps, and hashes from an authorized live validation;
- a complete normalized snapshot passes schema, provenance, geometry/CRS, freshness, duplicate,
  join-coverage, and deterministic status tests, with an immutable ID and reproducible manifest;
- atomic promotion and rollback are demonstrated with a synthetic failed refresh and a real
  last-known-good pointer check; first publication is demonstrated with no pointer and a handler
  `unknown` result;
- the deployed Demo capture check proves bounded, snapshot-pinned reads and correct `unknown`
  behavior for stale, missing, conflicting, unsupported, source-down, and boundary cases;
- operational refresh checks prove the 10 MiB response/page, 100 MiB raw-artifact, 10,000-record,
  2,000,000-vertex, 5-second Athena timeout, and 64 MiB scanned-bytes limits; 90-day raw-artifact
  and six-snapshot lifecycle policies; publisher/reader IAM separation; bounded retries,
  alerting, redacted evidence, and no unbounded Athena scan; and
- reviewer-approved evidence contains no secrets, personal data, raw messages, or unsupported
  claim that a live feed is continuously available.

## Non-goals

Municipal, conservation-authority, Indigenous-government, Parks Canada, or broader jurisdiction
coverage; generalized closures; RAG; Rust migration; autonomous legal advice or emergency action;
and real SMS sending are out of scope. A real SMS check requires separate explicit authorization
and is not implied by this spec. No source is declared continuously available merely because a
live check succeeded once.

## Sequencing and runbook expectations

Implement in this order: source/terms contract; raw and normalized snapshot manifest; parser and
offline fixtures; validation and deterministic promotion/rollback; bounded S3/Athena read path;
live source validation; Demo capture verification; then scheduled refresh and operational checks.
Keep implementation within this sequence and update future ideas separately.

The runbook must name the cadence, operator/manual refresh procedure, access/rate-limit handling,
stale thresholds, alert thresholds, retry/timeout bounds, cost and Athena limits, evidence
redaction, promotion, last-known-good rollback, source-outage response, and recovery validation.
It must explicitly state that Stage 9.2's local snapshot is the current implementation until all
acceptance gates pass.
