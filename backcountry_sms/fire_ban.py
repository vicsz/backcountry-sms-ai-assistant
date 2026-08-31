"""Bounded Ontario Parks fire-ban lookup for the Stage 9.2 static snapshot."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from itertools import combinations, pairwise
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import boto3

LOGGER = logging.getLogger(__name__)
FireStatus = Literal["fire_ban", "no_current_fire_ban_record", "unknown"]
Freshness = Literal["fresh", "stale", "missing"]
BoundaryOutcome = Literal["inside", "outside", "boundary", "invalid"]
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_ATHENA_COLUMNS = (
    "park_id",
    "park_name",
    "normalized_status",
    "source_as_of",
    "retrieved_at",
    "source_url",
    "source_hash",
    "raw_wording",
)


@dataclass(frozen=True)
class FireBanResult:
    park_name: str | None
    jurisdiction: str
    status: FireStatus
    source_as_of: str | None
    retrieved_at: str | None
    source_url: str | None
    source_hash: str | None
    snapshot_id: str | None
    freshness: Freshness
    raw_wording: str | None = None
    uncertainty: str | None = None
    boundary: BoundaryOutcome | None = None

    @property
    def confirmed(self) -> bool:
        return self.status != "unknown" and self.freshness == "fresh" and self.boundary == "inside"


@dataclass(frozen=True)
class StaticSnapshot:
    snapshot_id: str
    schema_version: str
    snapshot_created_at: str
    parks: tuple[dict[str, object], ...]
    statuses: tuple[dict[str, object], ...]


class FireBanQueryAdapter(Protocol):
    def query(self, snapshot_id: str, latitude: float, longitude: float) -> list[dict[str, object]]: ...


class AthenaFireBanQueryAdapter:
    """Bounded Athena adapter for a prepared, snapshot-pinned S3 dataset."""

    def __init__(self, client: object | None = None, *, database: str, table: str, output_location: str) -> None:
        self.client: Any = client or boto3.client("athena")
        if not _IDENTIFIER.fullmatch(database) or not _IDENTIFIER.fullmatch(table):
            raise ValueError("invalid_athena_identifier")
        if not re.fullmatch(r"s3://[A-Za-z0-9.!_-]{3,63}/[^\s]+", output_location):
            raise ValueError("invalid_athena_output_location")
        self.database, self.table, self.output_location = database, table, output_location

    def build_query(self, snapshot_id: str, latitude: float, longitude: float) -> str:
        _validate_point(latitude, longitude)
        if not snapshot_id or len(snapshot_id) > 128 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", snapshot_id):
            raise ValueError("invalid_snapshot_id")
        return (
            "SELECT park_id, park_name, normalized_status, source_as_of, retrieved_at, "
            "source_url, source_hash, raw_wording FROM " + self.table
            + " WHERE snapshot_id = '" + snapshot_id + "'"
            + " AND ST_Contains(ST_GeometryFromText(geometry_wkt), "
            + f"ST_Point({longitude:.8f}, {latitude:.8f})) LIMIT 2"
        )

    def query(self, snapshot_id: str, latitude: float, longitude: float) -> list[dict[str, object]]:
        execution_id = self.client.start_query_execution(
            QueryString=self.build_query(snapshot_id, latitude, longitude),
            QueryExecutionContext={"Database": self.database}, ResultConfiguration={"OutputLocation": self.output_location},
            WorkGroup=os.environ.get("ATHENA_WORKGROUP", "primary"),
        )["QueryExecutionId"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.client.get_query_execution(QueryExecutionId=execution_id)["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                return _athena_rows(self.client.get_query_results(QueryExecutionId=execution_id, MaxResults=3))
            if state in {"FAILED", "CANCELLED"}:
                raise RuntimeError("athena_query_failed")
            time.sleep(0.05)
        self.client.stop_query_execution(QueryExecutionId=execution_id)
        raise TimeoutError("athena_query_timeout")


def default_fixture_path() -> Path:
    return Path(__file__).parents[1] / "tests" / "fixtures" / "stage-9-2-fire-ban-snapshot.json"


def load_snapshot(path: Path | None = None) -> StaticSnapshot:
    payload = json.loads((path or default_fixture_path()).read_text())
    return StaticSnapshot(_text(payload, "snapshot_id"), _text(payload, "schema_version"), _text(payload, "snapshot_created_at"), tuple(payload.get("parks", [])), tuple(payload.get("statuses", [])))


def lookup(latitude: float, longitude: float, snapshot: StaticSnapshot | None = None, *, now: datetime | None = None, max_age_days: int = 14) -> FireBanResult:
    snapshot = snapshot or load_snapshot()
    current_time = now or datetime.now(UTC)
    try:
        _validate_point(latitude, longitude)
    except ValueError:
        return _unknown(snapshot, "missing", "invalid_coordinates")
    freshness = _freshness(snapshot.snapshot_created_at, current_time, max_age_days)
    if freshness != "fresh":
        return _unknown(snapshot, freshness, "stale_snapshot" if freshness == "stale" else "invalid_snapshot_time")
    validation_error = _validate_snapshot(snapshot, current_time)
    if validation_error:
        return _unknown(snapshot, freshness, validation_error)
    matches = [(park, outcome) for park in snapshot.parks if (outcome := point_in_wkt(latitude, longitude, cast(str, park["geometry_wkt"]))) in {"inside", "boundary"}]
    if any(outcome == "boundary" for _, outcome in matches):
        return _unknown(snapshot, freshness, "unresolved_boundary", boundary="boundary")
    if len(matches) != 1:
        return _unknown(snapshot, freshness, "park_not_found" if not matches else "conflicting_geometry", boundary="outside" if not matches else "boundary")
    park, boundary = matches[0]
    rows = [row for row in snapshot.statuses if row["park_id"] == park["park_id"]]
    if len(rows) > 1:
        return _unknown(snapshot, freshness, "conflicting_status_sources", boundary=boundary)
    status = rows[0] if rows else None
    normalized = status.get("normalized_status") if status else "no_current_fire_ban_record"
    if normalized not in {"active", "no_current_fire_ban_record"}:
        return _unknown(snapshot, freshness, "unsupported_status", boundary=boundary)
    return FireBanResult(cast(str, park["park_name"]), "Ontario Parks", "fire_ban" if normalized == "active" else "no_current_fire_ban_record", _text_or_none(status, "source_as_of"), _text_or_none(status, "retrieved_at") or snapshot.snapshot_created_at, _text_or_none(status, "source_url") or "https://www.ontarioparks.ca/alerts", _text_or_none(status, "source_hash"), snapshot.snapshot_id, freshness, _text_or_none(status, "raw_wording"), boundary=boundary)


def point_in_wkt(latitude: float, longitude: float, wkt: str) -> BoundaryOutcome:
    _validate_point(latitude, longitude)
    polygons = _parse_wkt(wkt)
    if any(_on_segment(longitude, latitude, ring) for polygon in polygons for ring in polygon):
        return "boundary"
    return "inside" if any(_inside_polygon(longitude, latitude, polygon) for polygon in polygons) else "outside"


def format_sms(result: FireBanResult) -> str:
    if result.status == "unknown":
        return f"Fire status unknown for {result.park_name or 'this point'}; verify Ontario Parks alerts."
    if result.status == "fire_ban":
        return f"{result.park_name}: Ontario Parks fire ban active as of {result.source_as_of or 'snapshot date'}. Verify alerts before travel."
    return f"{result.park_name}: no Ontario Parks fire-ban record in this snapshot. Verify current alerts; this does not mean fires are allowed."


def _unknown(snapshot: StaticSnapshot, freshness: Freshness, reason: str, *, boundary: BoundaryOutcome = "invalid") -> FireBanResult:
    return FireBanResult(None, "Ontario Parks", "unknown", None, snapshot.snapshot_created_at, "https://www.ontarioparks.ca/alerts", None, snapshot.snapshot_id, freshness, uncertainty=reason, boundary=boundary)


def _freshness(value: object, now: datetime, max_age_days: int) -> Freshness:
    if not isinstance(value, str) or now.tzinfo is None or now.utcoffset() is None or max_age_days < 0:
        return "missing"
    try:
        created = datetime.fromisoformat(value)
    except ValueError:
        return "missing"
    if created.tzinfo is None or created.utcoffset() is None or created > now:
        return "missing"
    return "fresh" if (now - created).total_seconds() <= max_age_days * 86400 else "stale"


def _validate_snapshot(snapshot: StaticSnapshot, now: datetime) -> str | None:
    required_park = ("park_id", "park_name", "geometry_wkt", "source_name", "source_url", "source_record_id", "source_hash")
    park_ids: set[object] = set()
    if not isinstance(snapshot.parks, (tuple, list)) or not isinstance(snapshot.statuses, (tuple, list)):
        return "malformed_snapshot_collections"
    for park in snapshot.parks:
        if not isinstance(park, dict):
            return "malformed_snapshot_collections"
        if any(not isinstance(park.get(key), str) or not park[key] for key in required_park):
            return "missing_geometry_provenance"
        try:
            _parse_wkt(cast(str, park["geometry_wkt"]))
        except ValueError:
            return "invalid_snapshot_geometry"
        park_ids.add(park["park_id"])
    required_status = ("source_name", "source_url", "source_record_id", "source_hash", "park_id", "snapshot_id", "normalized_status", "raw_wording", "source_as_of", "retrieved_at")
    for status in snapshot.statuses:
        if not isinstance(status, dict):
            return "malformed_snapshot_collections"
        if any(not isinstance(status.get(key), str) or not status[key] for key in required_status):
            return "missing_status_provenance"
        if status["snapshot_id"] != snapshot.snapshot_id or status["park_id"] not in park_ids or status["source_name"] != "Ontario Parks":
            return "inconsistent_status_snapshot"
        if not _valid_status_time(status.get("source_as_of"), now, allow_date=True) or not _valid_status_time(status.get("retrieved_at"), now):
            return "invalid_status_time"
    return None


def _parse_wkt(wkt: str) -> list[list[list[tuple[float, float]]]]:
    tokens = re.findall(r"[A-Za-z]+|[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?|[(),]", wkt)
    if not tokens or tokens[0].upper() not in {"POLYGON", "MULTIPOLYGON"} or tokens[-1] != ")":
        raise ValueError("invalid_geometry")
    kind, index = tokens[0].upper(), 1

    def group(position: int) -> tuple[list[object], int]:
        if position >= len(tokens) or tokens[position] != "(":
            raise ValueError("invalid_geometry")
        values: list[object] = []
        position += 1
        while position < len(tokens) and tokens[position] != ")":
            if tokens[position] == "(":
                child, position = group(position)
                values.append(child)
            else:
                if position + 1 >= len(tokens) or tokens[position].startswith(("(", ")", ",")) or tokens[position + 1].startswith(("(", ")", ",")):
                    raise ValueError("invalid_geometry")
                values.append((float(tokens[position]), float(tokens[position + 1])))
                position += 2
            if position < len(tokens) and tokens[position] == ",":
                position += 1
            elif position < len(tokens) and tokens[position] != ")":
                raise ValueError("invalid_geometry")
        if position >= len(tokens):
            raise ValueError("invalid_geometry")
        return values, position + 1

    parsed, index = group(index)
    if index != len(tokens):
        raise ValueError("invalid_geometry")
    polygons = [parsed] if kind == "POLYGON" else parsed
    output: list[list[list[tuple[float, float]]]] = []
    try:
        for polygon in cast(list[list[object]], polygons):
            rings: list[list[tuple[float, float]]] = []
            for ring in polygon:
                points = cast(list[tuple[float, float]], ring)
                if len(points) < 4 or points[0] != points[-1] or any(not math.isfinite(v) for point in points for v in point):
                    raise ValueError("invalid_geometry")
                rings.append(points)
            if not rings:
                raise ValueError("invalid_geometry")
            output.append(rings)
    except (TypeError, ValueError):
        raise ValueError("invalid_geometry") from None
    _validate_geometry_topology(output)
    return output


def _validate_geometry_topology(polygons: list[list[list[tuple[float, float]]]]) -> None:
    """Reject geometry that the small deterministic membership algorithm cannot trust."""
    for polygon in polygons:
        outer = polygon[0]
        _validate_ring(outer)
        for hole in polygon[1:]:
            _validate_ring(hole)
            if _rings_intersect(hole, outer) or _ring_relation(hole, outer) != "inside":
                raise ValueError("invalid_geometry")
        for first_hole, second_hole in combinations(polygon[1:], 2):
            if _rings_intersect(first_hole, second_hole) or _inside(*first_hole[0], second_hole) or _inside(*second_hole[0], first_hole):
                raise ValueError("invalid_geometry")

    for first_index, first_polygon in enumerate(polygons):
        for second_polygon in polygons[first_index + 1:]:
            if any(_rings_intersect(first_ring, second_ring) for first_ring in first_polygon for second_ring in second_polygon):
                raise ValueError("invalid_geometry")
            if _inside(*first_polygon[0][0], second_polygon[0]) or _inside(*second_polygon[0][0], first_polygon[0]):
                raise ValueError("invalid_geometry")


def _validate_ring(ring: list[tuple[float, float]]) -> None:
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("invalid_geometry")
    if any(not -180 <= x <= 180 or not -90 <= y <= 90 for x, y in ring):
        raise ValueError("invalid_geometry")
    if any(first == second for first, second in pairwise(ring[:-1])):
        raise ValueError("invalid_geometry")
    area = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pairwise(ring))) / 2
    if area <= 1e-12:
        raise ValueError("invalid_geometry")
    segments = list(pairwise(ring))
    for first_index, first in enumerate(segments):
        for second_index, second in enumerate(segments):
            if second_index <= first_index or second_index == first_index + 1:
                continue
            if first_index == 0 and second_index == len(segments) - 1:
                continue
            if _segments_intersect(first, second):
                raise ValueError("invalid_geometry")


def _ring_relation(ring: list[tuple[float, float]], container: list[tuple[float, float]]) -> str:
    if any(_on_segment(x, y, container) for x, y in ring[:-1]):
        return "boundary"
    return "inside" if all(_inside(x, y, container) for x, y in ring[:-1]) else "outside"


def _valid_status_time(value: object, now: datetime, *, allow_date: bool = False) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if allow_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value) <= now.date()
        except ValueError:
            return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None and parsed <= now


def _rings_intersect(first: list[tuple[float, float]], second: list[tuple[float, float]]) -> bool:
    return any(_segments_intersect(a, b) for a in pairwise(first) for b in pairwise(second))


def _segments_intersect(first: tuple[tuple[float, float], tuple[float, float]], second: tuple[tuple[float, float], tuple[float, float]]) -> bool:
    def orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    a, b = first
    c, d = second
    epsilon = 1e-12
    values = (orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b))
    if all(value > epsilon for value in values[:2]) or all(value < -epsilon for value in values[:2]):
        return False
    if all(value > epsilon for value in values[2:]) or all(value < -epsilon for value in values[2:]):
        return False
    if all(abs(value) > epsilon for value in values):
        return True
    return _on_segment(*c, [a, b]) or _on_segment(*d, [a, b]) or _on_segment(*a, [c, d]) or _on_segment(*b, [c, d])


def _inside_polygon(x: float, y: float, polygon: list[list[tuple[float, float]]]) -> bool:
    return _inside(x, y, polygon[0]) and not any(_inside(x, y, hole) for hole in polygon[1:])


def _on_segment(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    for (x1, y1), (x2, y2) in pairwise(ring):
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) < 1e-10 and min(x1, x2) - 1e-10 <= x <= max(x1, x2) + 1e-10 and min(y1, y2) - 1e-10 <= y <= max(y1, y2) + 1e-10:
            return True
    return False


def _inside(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in pairwise(ring):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _athena_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    result_set = payload.get("ResultSet")
    if not isinstance(result_set, dict) or not isinstance(result_set.get("Rows"), list):
        raise TypeError("athena_malformed_results")
    rows = result_set["Rows"]
    if not rows:
        return []
    if not all(isinstance(row, dict) for row in rows):
        raise TypeError("athena_malformed_row")
    typed_rows = cast(list[dict[str, object]], rows)
    header_data = typed_rows[0].get("Data")
    if not isinstance(header_data, list) or len(header_data) != len(_ATHENA_COLUMNS):
        raise TypeError("athena_missing_headers")
    headers = []
    for cell in header_data:
        if not isinstance(cell, dict) or not isinstance(cell.get("VarCharValue"), str):
            raise TypeError("athena_missing_headers")
        headers.append(cell["VarCharValue"])
    if tuple(headers) != _ATHENA_COLUMNS:
        raise TypeError("athena_missing_headers")
    output: list[dict[str, object]] = []
    for row in typed_rows[1:3]:
        row_data = row.get("Data")
        if not isinstance(row_data, list) or len(row_data) != len(_ATHENA_COLUMNS):
            raise TypeError("athena_malformed_row")
        mapped: dict[str, object] = {}
        for header, cell in zip(_ATHENA_COLUMNS, row_data, strict=True):
            if not isinstance(cell, dict):
                raise TypeError("athena_malformed_cell")
            value = cell.get("VarCharValue")
            if not isinstance(value, str) or not value.strip():
                raise TypeError("athena_malformed_cell")
            mapped[header] = value
        output.append(mapped)
    return output


def _validate_point(latitude: float, longitude: float) -> None:
    if not isinstance(latitude, (int, float)) or isinstance(latitude, bool) or not isinstance(longitude, (int, float)) or isinstance(longitude, bool) or not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("invalid_coordinates")


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing_{key}")
    return value


def _text_or_none(payload: dict[str, object] | None, key: str) -> str | None:
    value = payload.get(key) if payload else None
    return value if isinstance(value, str) else None
