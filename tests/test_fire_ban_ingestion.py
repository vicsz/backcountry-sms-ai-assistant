from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backcountry_sms import fire_ban_ingestion

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def park_payload() -> dict[str, object]:
    return {
        "features": [
            {
                "attributes": {
                    "PROTECTED_SITE_IDENT": "ONP-1",
                    "PROTECTED_AREA_NAME_ENG": "Example Provincial Park",
                    "GEOMETRY_UPDATE_DATETIME": 0,
                },
                "geometry": {"rings": [[[-79.5, 45.0], [-79.2, 45.0], [-79.2, 45.3], [-79.5, 45.3], [-79.5, 45.0]]]},
            }
        ]
    }


def test_arcgis_normalization_preserves_geometry_and_provenance() -> None:
    parks = fire_ban_ingestion.normalize_arcgis_features(
        park_payload(),
        source_name="Ontario LIO Provincial Park Regulated",
        source_url=fire_ban_ingestion.PARK_SOURCE_URL,
        source_hash="sha256:park",
        retrieved_at=NOW.isoformat(),
        id_field="PROTECTED_SITE_IDENT",
        name_field="PROTECTED_AREA_NAME_ENG",
    )
    assert parks[0]["park_id"] == "ONP-1"
    assert parks[0]["geometry_wkt"].startswith("POLYGON ((-79.50000000 45.00000000")
    assert parks[0]["source_hash"] == "sha256:park"


def test_alert_normalization_is_explicit_and_snapshot_is_deterministic() -> None:
    statuses = fire_ban_ingestion.normalize_fire_ban_alerts(
        [{"park_id": "ONP-1", "park_name": "Example Provincial Park", "alert_type": "fire ban", "raw_wording": "This park is currently under a fire ban.", "source_as_of": "2026-09-05"}],
        source_hash="sha256:alerts",
        retrieved_at=NOW.isoformat(),
    )
    parks = fire_ban_ingestion.normalize_arcgis_features(
        park_payload(),
        source_name="Ontario LIO Provincial Park Regulated",
        source_url=fire_ban_ingestion.PARK_SOURCE_URL,
        source_hash="sha256:park",
        retrieved_at=NOW.isoformat(),
        id_field="PROTECTED_SITE_IDENT",
        name_field="PROTECTED_AREA_NAME_ENG",
    )
    first = fire_ban_ingestion.build_snapshot(parks, statuses, snapshot_created_at=NOW.isoformat())
    second = fire_ban_ingestion.build_snapshot(parks, statuses, snapshot_created_at=NOW.isoformat())
    assert first == second
    assert first["statuses"][0]["snapshot_id"] == first["snapshot_id"]


def test_invalid_snapshot_does_not_change_local_current_pointer(tmp_path: Path) -> None:
    parks = fire_ban_ingestion.normalize_arcgis_features(
        park_payload(),
        source_name="Ontario LIO Provincial Park Regulated",
        source_url=fire_ban_ingestion.PARK_SOURCE_URL,
        source_hash="sha256:park",
        retrieved_at=NOW.isoformat(),
        id_field="PROTECTED_SITE_IDENT",
        name_field="PROTECTED_AREA_NAME_ENG",
    )
    statuses = fire_ban_ingestion.normalize_fire_ban_alerts(
        [{"park_id": "ONP-1", "park_name": "Example Provincial Park", "alert_type": "fire ban", "raw_wording": "Fire ban in effect."}],
        source_hash="sha256:alerts",
        retrieved_at=NOW.isoformat(),
    )
    snapshot = fire_ban_ingestion.build_snapshot(parks, statuses, snapshot_created_at=NOW.isoformat())
    fire_ban_ingestion.promote_local_snapshot(snapshot, tmp_path, now=NOW)
    pointer = json.loads((tmp_path / "current.json").read_text())
    invalid = dict(snapshot, snapshot_id="bad", statuses=[dict(statuses[0], snapshot_id="bad", source_as_of="not-a-date")])
    with pytest.raises(ValueError):
        fire_ban_ingestion.promote_local_snapshot(invalid, tmp_path, now=NOW)
    assert json.loads((tmp_path / "current.json").read_text()) == pointer
