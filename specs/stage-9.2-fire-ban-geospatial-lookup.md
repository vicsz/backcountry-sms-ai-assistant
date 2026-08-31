# Stage 9.2 — Static Ontario Parks fire-ban geospatial lookup MVP

Status: Implemented locally; live Athena/S3 execution, measurement, and deployment deferred

## Objective

Provide a bounded, source-backed fire-ban lookup for Ontario provincial parks using versioned
static data in S3, Athena geospatial queries, and handler support. The MVP must identify the park
containing a normalized request point and return the latest status represented by the prepared
snapshot, with explicit freshness and uncertainty. It must not imply that absence of a record means
fires are legally permitted.

## In-scope sources

The MVP uses two prepared source datasets. Preparation is manual or offline; scheduled retrieval,
parsing, and promotion are deferred to `specs/stage-9.2.1-fire-ban-geospatial-ingestion.md`.

The offline contract is represented by `tests/fixtures/stage-9-2-fire-ban-snapshot.json`. It is a
versioned, source-labelled test snapshot (not a claim that it is a current legal status feed). The
runtime lookup is in `backcountry_sms/fire_ban.py`; its `FireBanQueryAdapter` contract and bounded
`AthenaFireBanQueryAdapter` pin each query to a snapshot ID. No live query is wired into the handler.

1. Ontario Parks fire-ban alerts are the primary park-level status source. Preserve the park name,
   alert URL, alert type, source wording, and the page's "as of" value. The initial normalized alert
   types are `fire_ban` and `no_current_fire_ban_record`; the latter is an absence in the snapshot,
   not a legal conclusion.
2. Ontario's LIO `Provincial Park Regulated` polygon layer identifies park membership and supplies
   stable park identifiers and geometry provenance. Use the official English name and identifier
   to join the status snapshot to the geometry.

The Ontario Restricted Fire Zone polygon layer may be included as a separately labeled provincial
restriction source if it can be prepared without expanding the MVP. It must not be merged silently
with an Ontario Parks alert. Conflicting or incomplete source results return uncertainty.

Reference sources:

- [Ontario Parks alerts](https://www.ontarioparks.ca/alerts)
- [Ontario LIO Provincial Park Regulated layer](https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open03/MapServer/4)
- [Ontario LIO Restricted Fire Zone layer](https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open08/MapServer/28)

## Static data contract

Store the original source artifacts and normalized query tables under versioned S3 prefixes. The
normalized tables must retain:

- `source_name`, `source_url`, `source_record_id`, and `source_hash`;
- `jurisdiction` and `park_id`;
- `park_name`, `alert_type`, `normalized_status`, and exact `raw_wording`;
- `source_as_of`, `published_at` when available, `retrieved_at`, and `effective_at` when available;
- `geometry_wkt` in longitude/latitude order for park polygons;
- source geometry update/effective timestamps when supplied;
- `snapshot_id`, `snapshot_created_at`, and a schema/version identifier.

Parquet is the preferred normalized format. Athena table definitions and query results must be
version-pinned to the snapshot and must not scan an unbounded S3 prefix.

## Lookup behavior

- Accept only a normalized point from the existing location-intelligence path for this MVP.
- Find the containing park with a deterministic polygon intersection. Boundary points must be
  treated explicitly; do not replace a failed intersection with the nearest park.
- Join the park identifier to the Ontario Parks status snapshot.
- Return `fire_ban` only when the snapshot contains an active Ontario Parks fire-ban record.
- Return `unknown` when the park is not found, the snapshot is stale, geometry is missing or
  invalid, the sources conflict, Athena fails, or the requested point is on an unresolved boundary.
- A park with no fire-ban row may be reported as “no Ontario Parks fire-ban record in this
  snapshot,” accompanied by the snapshot freshness and a reminder to verify current alerts. It must
  not be rendered as “fires are allowed” or “no ban.”
- Keep the fire lookup failure independent from weather lookup. A fire-source failure must not
  suppress an otherwise valid weather response.

The handler may recognize an explicit fire-ban/fire-status request and invoke the lookup. Natural
language relevance classification may select the tool, but deterministic source data owns the
status, jurisdiction, geometry, timestamps, and wording.

## Response and safety boundary

Return a concise source-backed result containing, where known:

- park name and jurisdiction;
- normalized status or explicit uncertainty;
- source as-of/retrieved time;
- a short source label or URL.

Do not provide broad legal advice, autonomous emergency decisions, or an uncited claim that fires
are permitted. Preserve exact source wording in the structured result and use only a concise
paraphrase in the SMS response.

## Offline evaluation requirements

Fixtures must cover:

- Burnt Island Lake inside Algonquin Provincial Park;
- a point outside a park;
- a point inside a park with an active fire-ban record;
- a park with no fire-ban record in the snapshot;
- polygon boundaries and unresolved boundary behavior;
- missing/invalid geometry;
- stale snapshots and Athena/query failure;
- source-version/hash preservation;
- conflicting Ontario Parks and optional RFZ results;
- one-segment SMS formatting and refusal to invent status.

Every fixture must include source authority, expected park, expected status, snapshot freshness, and
whether the result is safe to state as confirmed.

## Acceptance criteria and non-goals

- A versioned Ontario Parks alert snapshot and official provincial-park polygon snapshot are
  documented locally, and the bounded Athena adapter is queryable against a prepared S3 table;
  live S3 publication and Athena execution remain deferred.
- A deterministic query returns park membership, status, provenance, and freshness for the offline
  fixtures.
- The handler can invoke the lookup with bounded independent failure behavior and concise output.
- No automated ingestion, web scraping, scheduled refresh, municipal fire-ban coverage,
  conservation-authority coverage, Indigenous-government coverage, or broad closure taxonomy is
  implemented by this stage.
- No deployment, live source/provider check, or SMS send is authorized by this spec.

## Implementation state

Implemented locally: deterministic longitude/latitude WKT `POLYGON` hole and `MULTIPOLYGON`
membership with explicit inside/outside/boundary/invalid outcomes and strict ring topology;
snapshot-wide geometry and
provenance validation; finite coordinate and timezone-aware freshness validation; typed
park/status/provenance/freshness results; stale, future, missing, invalid, unsupported, and
conflicting-data uncertainty; snapshot-pinned Athena result translation with defensive schema,
cell-shape, and completeness validation, bounded failure, and
timeout cancellation; explicit fire-status handler requests; and independent optional fire lookup
during weather requests. Successful combined weather/fire requests append the fire result
deterministically within one SMS segment without adding a model call. The offline benchmark
reports repeatable local p50/p95 lookup timing only. Live Athena execution timing, S3 snapshot
publication, and infrastructure wiring remain deferred to a reviewed live step and Stage 9.2.1.
