"""Offline-safe fire-ban source normalization and atomic local promotion.

This module deliberately stops at normalized, provenance-preserving artifacts. It does not
schedule refreshes, modify AWS resources, or make the deployed handler read a new snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from backcountry_sms import fire_ban

PARK_SOURCE_URL = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open03/MapServer/4"
FIRE_ZONE_SOURCE_URL = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open08/MapServer/28"
ALERT_SOURCE_URL = "https://www.ontarioparks.ca/alerts"
SCHEMA_VERSION = "stage-9.2.v2"
MAX_SOURCE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class SourceArtifact:
    source_name: str
    source_url: str
    retrieved_at: str
    content_type: str
    sha256: str
    body: bytes


def retrieve_source(url: str, *, source_name: str, timeout_seconds: float = 10.0, max_bytes: int = MAX_SOURCE_BYTES) -> SourceArtifact:
    """Retrieve one bounded source resource; callers must decide whether to promote it."""
    if not url.startswith("https://"):
        raise ValueError("https_source_required")
    request = Request(url, headers={"User-Agent": "backcountry-fire-ban-ingestion/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("source_response_exceeds_limit")
        content_type = response.headers.get_content_type()
    return SourceArtifact(source_name, url, datetime.now(UTC).isoformat(), content_type, sha256(body), body)


def sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def normalize_arcgis_features(
    payload: Mapping[str, Any],
    *,
    source_name: str,
    source_url: str,
    source_hash: str,
    retrieved_at: str,
    id_field: str,
    name_field: str,
) -> list[dict[str, Any]]:
    """Normalize ArcGIS polygon features into the snapshot's WKT/provenance shape."""
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("arcgis_features_missing")
    records: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, Mapping) or not isinstance(feature.get("attributes"), Mapping):
            raise TypeError("arcgis_feature_malformed")
        attributes = feature["attributes"]
        record_id = attributes.get(id_field)
        name = attributes.get(name_field)
        geometry = feature.get("geometry")
        if not record_id or not name or not isinstance(geometry, Mapping):
            raise ValueError("arcgis_feature_provenance_missing")
        rings = geometry.get("rings")
        if not isinstance(rings, list) or not rings:
            raise ValueError("arcgis_polygon_missing")
        wkt = _rings_to_wkt(rings)
        records.append(
            {
                "park_id": str(record_id),
                "park_name": str(name),
                "geometry_wkt": wkt,
                "source_name": source_name,
                "source_url": source_url,
                "source_record_id": str(record_id),
                "source_hash": source_hash,
                "source_as_of": str(attributes.get("GEOMETRY_UPDATE_DATETIME") or attributes.get("EFFECTIVE_DATETIME") or retrieved_at),
            }
        )
    return records


def normalize_fire_ban_alerts(
    records: list[Mapping[str, Any]],
    *,
    source_url: str = ALERT_SOURCE_URL,
    source_hash: str,
    retrieved_at: str,
) -> list[dict[str, Any]]:
    """Normalize explicitly extracted Ontario Parks fire-ban alert records.

    HTML extraction is intentionally separate: an unreviewed page layout must not silently turn
    arbitrary alert text into a legal status. The records passed here are the parser contract.
    """
    normalized: list[dict[str, Any]] = []
    for record in records:
        park_name = str(record.get("park_name") or "").strip()
        wording = str(record.get("raw_wording") or "").strip()
        alert_type = str(record.get("alert_type") or "").strip().casefold()
        if not park_name or not wording or alert_type != "fire ban":
            raise ValueError("unsupported_alert_record")
        normalized.append(
            {
                "source_name": "Ontario Parks",
                "source_url": str(record.get("source_url") or source_url),
                "source_record_id": str(record.get("source_record_id") or f"{park_name}:fire-ban"),
                "source_hash": source_hash,
                "jurisdiction": "Ontario Parks",
                "park_id": str(record.get("park_id") or park_name),
                "park_name": park_name,
                "alert_type": "fire_ban",
                "normalized_status": "active",
                "raw_wording": wording,
                "source_as_of": str(record.get("source_as_of") or retrieved_at),
                "retrieved_at": retrieved_at,
            }
        )
    return normalized


def build_snapshot(
    parks: list[Mapping[str, Any]],
    statuses: list[Mapping[str, Any]],
    *,
    snapshot_created_at: str,
) -> dict[str, Any]:
    """Build a deterministic snapshot payload; no pointer is changed here."""
    content = {"schema_version": SCHEMA_VERSION, "parks": parks, "statuses": statuses, "snapshot_created_at": snapshot_created_at}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    snapshot_id = f"ontario-parks-{digest}"
    normalized_statuses = [dict(status, snapshot_id=snapshot_id) for status in statuses]
    return {"schema_version": SCHEMA_VERSION, "snapshot_id": snapshot_id, "snapshot_created_at": snapshot_created_at, "parks": [dict(park) for park in parks], "statuses": normalized_statuses}


def promote_local_snapshot(snapshot: Mapping[str, Any], destination: Path, *, now: datetime | None = None) -> Path:
    """Atomically write a validated local snapshot and current pointer.

    This is a local promotion primitive for tests and operator review. It is not the deployed
    S3/Athena publisher and is deliberately not called by the Lambda runtime.
    """
    payload = dict(snapshot)
    snapshot_id = payload.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", snapshot_id):
        raise ValueError("invalid_snapshot_id")
    snapshot_path = destination / "snapshots" / f"{snapshot_id}.json"
    current_path = destination / "current.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    _validate_payload(payload, now=now)
    _atomic_json_write(snapshot_path, payload)
    _atomic_json_write(current_path, {"snapshot_id": payload["snapshot_id"], "promoted_at": (now or datetime.now(UTC)).isoformat()})
    return snapshot_path


def _validate_payload(payload: Mapping[str, Any], *, now: datetime | None) -> None:
    snapshot = fire_ban.StaticSnapshot(
        str(payload.get("snapshot_id", "")),
        str(payload.get("schema_version", "")),
        str(payload.get("snapshot_created_at", "")),
        tuple(payload.get("parks", [])),
        tuple(payload.get("statuses", [])),
    )
    error = fire_ban.validate_snapshot(snapshot, now=now or datetime.now(UTC))
    if error:
        raise ValueError(error)


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        os.unlink(temporary)
        raise


def _rings_to_wkt(rings: list[Any]) -> str:
    if len(rings) != 1:
        raise ValueError("arcgis_complex_polygon_requires_review")
    parsed: list[str] = []
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError("arcgis_ring_malformed")
        points = []
        for point in ring:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("arcgis_coordinate_malformed")
            points.append(f"{float(point[0]):.8f} {float(point[1]):.8f}")
        if points[0] != points[-1]:
            raise ValueError("arcgis_ring_not_closed")
        parsed.append(f"({', '.join(points)})")
    return f"POLYGON ({', '.join(parsed)})"
