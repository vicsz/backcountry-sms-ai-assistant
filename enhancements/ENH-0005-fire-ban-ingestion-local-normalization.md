# ENH-0005 — Fire-ban ingestion normalization and local promotion primitive

## Status

Partially implemented — offline normalization and atomic local promotion are complete. Live
source extraction, scheduled refresh, AWS publication, and Demo verification remain deferred
under [Stage 9.2.1](../specs/stage-9.2.1-fire-ban-geospatial-ingestion.md).

## Implemented

- Bounded source retrieval records URL, content type, UTC retrieval time, and SHA-256 hash.
- ArcGIS polygon feature normalization preserves park identifiers, WKT geometry, source fields,
  and source timestamps; complex multi-ring geometry is rejected for explicit review rather than
  being silently misrepresented.
- Explicit Ontario Parks fire-ban alert records normalize only the supported active status; an
  unreviewed HTML layout cannot silently become a status record.
- Snapshot IDs are deterministic from normalized content and statuses are snapshot-pinned.
- A local atomic writer proves that invalid snapshots leave the previous `current.json` pointer
  untouched.
- Synthetic tests cover provenance, deterministic IDs, validation failure, and rollback safety.

## Deferred

- Terms/availability approval and a parser contract against the live Ontario Parks alerts page.
- Live source validation, raw-artifact retention, source coverage reconciliation, and geometry
  quality checks against the official LIO layers.
- S3/Athena publication, IAM separation, lifecycle policy, scheduled refresh, monitoring, and
  deployed Demo capture verification.
- Any real SMS check.

## Acceptance tests completed

- `tests/test_fire_ban.py`
- `tests/test_fire_ban_ingestion.py`

The local primitive is not wired into the Lambda or CDK and must not be described as a live feed.
