from datetime import UTC, datetime
from pathlib import Path
from statistics import quantiles
from time import perf_counter

import pytest

from backcountry_sms import fire_ban, handler
from backcountry_sms.models import LocationCandidate, LocationResolution

pytestmark = pytest.mark.legacy_python_runtime

FIXTURE = Path(__file__).parent / "fixtures" / "stage-9-2-fire-ban-snapshot.json"
NOW = datetime(2026, 8, 21, 12, tzinfo=UTC)


def test_burnt_island_lake_and_portage_store_are_inside_algonquin() -> None:
    snapshot = fire_ban.load_snapshot(FIXTURE)
    for point in ((45.64, -78.62), (45.70, -78.55)):
        result = fire_ban.lookup(*point, snapshot, now=NOW)
        assert result.park_name == "Algonquin Provincial Park"
        assert result.status == "no_current_fire_ban_record"
        assert result.freshness == "fresh"
        assert result.confirmed


def test_active_no_record_outside_and_boundary_are_explicit() -> None:
    snapshot = fire_ban.load_snapshot(FIXTURE)
    active = fire_ban.lookup(45.15, -79.35, snapshot, now=NOW)
    no_record = fire_ban.lookup(44.65, -79.85, snapshot, now=NOW)
    outside = fire_ban.lookup(43.0, -75.0, snapshot, now=NOW)
    boundary = fire_ban.lookup(45.50, -78.60, snapshot, now=NOW)
    assert active.status == "fire_ban" and active.park_name == "Active Fixture Provincial Park"
    assert no_record.status == "no_current_fire_ban_record"
    assert outside.uncertainty == "park_not_found" and outside.boundary == "outside"
    assert boundary.status == "unknown" and boundary.uncertainty == "unresolved_boundary"


def test_polygon_holes_and_multipolygon_have_explicit_boundary_behavior() -> None:
    donut = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), (2 2, 8 2, 8 8, 2 8, 2 2))"
    multi = "MULTIPOLYGON (((20 0, 30 0, 30 10, 20 10, 20 0)), ((40 0, 50 0, 50 10, 40 10, 40 0)))"
    assert fire_ban.point_in_wkt(1, 1, donut) == "inside"
    assert fire_ban.point_in_wkt(5, 5, donut) == "outside"
    assert fire_ban.point_in_wkt(2, 5, donut) == "boundary"
    assert fire_ban.point_in_wkt(5, 5, multi) == "outside"
    assert fire_ban.point_in_wkt(5, 25, multi) == "inside"
    assert fire_ban.point_in_wkt(0, 25, multi) == "boundary"


def test_invalid_wkt_topology_fails_closed() -> None:
    invalid_geometries = (
        "POLYGON ((0 0, 2 2, 0 2, 2 0, 0 0))",  # self-intersection
        "POLYGON ((0 0, 1 0, 2 0, 0 0))",  # zero area
        "POLYGON ((-181 0, -180 0, -180 1, -181 0))",  # out of longitude range
        "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), (2 2, 12 2, 12 8, 2 8, 2 2))",  # hole escapes shell
        "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), (1 1, 5 1, 5 5, 1 5, 1 1), (4 4, 8 4, 8 8, 4 8, 4 4))",  # holes overlap
        "POLYGON ((0 0, 6 0, 6 2, 2 2, 2 6, 0 6, 0 0), (1 1, 5 1, 1 5, 1 1))",  # hole edge crosses concave shell
        "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), (1 1, 2 1, 2 2, 0 2, 1 1))",  # hole touches shell at a vertex
    )
    for wkt in invalid_geometries:
        try:
            fire_ban.point_in_wkt(1, 1, wkt)
        except ValueError as error:
            assert str(error) == "invalid_geometry"
        else:
            raise AssertionError("invalid WKT accepted")


def test_stale_missing_invalid_and_conflicting_data_return_unknown() -> None:
    snapshot = fire_ban.load_snapshot(FIXTURE)
    assert fire_ban.lookup(45.64, -78.62, snapshot, now=datetime(2026, 9, 10, tzinfo=UTC)).uncertainty == "stale_snapshot"
    invalid = fire_ban.StaticSnapshot(snapshot.snapshot_id, snapshot.schema_version, "not-a-date", snapshot.parks, snapshot.statuses)
    assert fire_ban.lookup(45.64, -78.62, invalid, now=NOW).freshness == "missing"
    bad_parks = ({"park_id": "BAD", "park_name": "Bad", "geometry_wkt": "POLYGON ((bad))", "source_name": "LIO", "source_url": "https://example.invalid", "source_record_id": "bad", "source_hash": "sha256:bad"},)
    bad = fire_ban.StaticSnapshot("bad", "v1", snapshot.snapshot_created_at, bad_parks, ())
    assert fire_ban.lookup(45.64, -78.62, bad, now=NOW).uncertainty == "invalid_snapshot_geometry"
    missing = fire_ban.StaticSnapshot("missing", "v1", snapshot.snapshot_created_at, (dict(bad_parks[0], geometry_wkt=None),), ())
    assert fire_ban.lookup(45.64, -78.62, missing, now=NOW).uncertainty == "missing_geometry_provenance"
    conflicting = fire_ban.StaticSnapshot(snapshot.snapshot_id, snapshot.schema_version, snapshot.snapshot_created_at, snapshot.parks, snapshot.statuses + (dict(snapshot.statuses[0]),))
    assert fire_ban.lookup(45.15, -79.35, conflicting, now=NOW).uncertainty == "conflicting_status_sources"
    unsupported = dict(snapshot.statuses[0], normalized_status="closed")
    unsupported_snapshot = fire_ban.StaticSnapshot(snapshot.snapshot_id, snapshot.schema_version, snapshot.snapshot_created_at, snapshot.parks, (unsupported,))
    assert fire_ban.lookup(45.15, -79.35, unsupported_snapshot, now=NOW).uncertainty == "unsupported_status"
    assert fire_ban.lookup(float("nan"), -78.62, snapshot, now=NOW).uncertainty == "invalid_coordinates"
    assert fire_ban.lookup(45.64, -78.62, snapshot, now=NOW.replace(tzinfo=None)).uncertainty == "invalid_snapshot_time"
    future = fire_ban.StaticSnapshot(snapshot.snapshot_id, snapshot.schema_version, "2026-08-22T12:00:00Z", snapshot.parks, snapshot.statuses)
    assert fire_ban.lookup(45.64, -78.62, future, now=NOW).uncertainty == "invalid_snapshot_time"


def test_malformed_snapshot_collections_and_status_times_fail_closed() -> None:
    snapshot = fire_ban.load_snapshot(FIXTURE)
    for malformed in (
        fire_ban.StaticSnapshot(snapshot.snapshot_id, snapshot.schema_version, snapshot.snapshot_created_at, (None,), snapshot.statuses),
        fire_ban.StaticSnapshot(snapshot.snapshot_id, snapshot.schema_version, snapshot.snapshot_created_at, snapshot.parks, (None,)),
        fire_ban.StaticSnapshot(snapshot.snapshot_id, snapshot.schema_version, snapshot.snapshot_created_at, None, snapshot.statuses),
    ):
        result = fire_ban.lookup(45.64, -78.62, malformed, now=NOW)
        assert result.status == "unknown" and result.uncertainty == "malformed_snapshot_collections"
    for changes in (
        {"retrieved_at": "2026-08-21T12:00:00"},
        {"retrieved_at": "not-a-timestamp"},
        {"retrieved_at": "2026-08-22T12:00:00Z"},
        {"source_as_of": "2026-08-22"},
    ):
        status = dict(snapshot.statuses[0], **changes)
        malformed = fire_ban.StaticSnapshot(snapshot.snapshot_id, snapshot.schema_version, snapshot.snapshot_created_at, snapshot.parks, (status,))
        result = fire_ban.lookup(45.15, -79.35, malformed, now=NOW)
        assert result.status == "unknown" and result.uncertainty == "invalid_status_time"


def test_provenance_and_one_segment_output() -> None:
    result = fire_ban.lookup(45.15, -79.35, fire_ban.load_snapshot(FIXTURE), now=NOW)
    assert result.source_url == "https://www.ontarioparks.ca/alerts"
    assert result.source_hash == "sha256:fixture-active-001"
    assert result.snapshot_id == "ontario-parks-fixture-2026-08-20"
    sms = fire_ban.format_sms(result)
    assert len(sms) <= 160
    no_record = fire_ban.lookup(45.64, -78.62, fire_ban.load_snapshot(FIXTURE), now=NOW)
    assert fire_ban.format_sms(no_record).startswith("Algonquin Provincial Park: no Ontario Parks fire-ban record")


def test_athena_query_is_snapshot_pinned_and_bounded() -> None:
    adapter = fire_ban.AthenaFireBanQueryAdapter(client=object(), database="db", table="fire_status", output_location="s3://bucket/results")
    query = adapter.build_query("snapshot-1", 45.64, -78.62)
    assert "snapshot_id = 'snapshot-1'" in query
    assert "LIMIT 2" in query
    for point in ((float("nan"), -78.62), (45.64, float("inf"))):
        try:
            adapter.build_query("snapshot-1", *point)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid Athena point accepted")


class FakeAthena:
    def __init__(self, states: list[str]) -> None:
        self.states = states
        self.stopped: list[str] = []

    def start_query_execution(self, **kwargs: object) -> dict[str, str]:
        return {"QueryExecutionId": "query-1"}

    def get_query_execution(self, **kwargs: object) -> dict[str, object]:
        return {"QueryExecution": {"Status": {"State": self.states.pop(0)}}}

    def get_query_results(self, **kwargs: object) -> dict[str, object]:
        columns = ["park_id", "park_name", "normalized_status", "source_as_of", "retrieved_at", "source_url", "source_hash", "raw_wording"]
        return {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": column} for column in columns]}, {"Data": [{"VarCharValue": value} for value in ("p1", "Algonquin", "active", "2026-08-19", "2026-08-20T12:00:00Z", "https://example.invalid", "sha256:test", "Fire ban in effect.")]}]}}

    def stop_query_execution(self, **kwargs: object) -> None:
        self.stopped.append(str(kwargs["QueryExecutionId"]))


def test_athena_success_maps_named_columns_and_failures_are_bounded(monkeypatch) -> None:
    client = FakeAthena(["RUNNING", "SUCCEEDED"])
    adapter = fire_ban.AthenaFireBanQueryAdapter(client=client, database="db", table="fire_status", output_location="s3://bucket/results")
    rows = adapter.query("snapshot-1", 45.64, -78.62)
    assert rows[0]["park_id"] == "p1" and rows[0]["normalized_status"] == "active"
    for kwargs in ({"database": "bad-name", "table": "t", "output_location": "s3://bucket/results"}, {"database": "db", "table": "t", "output_location": "not-s3"}):
        try:
            fire_ban.AthenaFireBanQueryAdapter(client=object(), **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid Athena input accepted")
    timed = FakeAthena(["RUNNING"] * 200)
    adapter = fire_ban.AthenaFireBanQueryAdapter(client=timed, database="db", table="t", output_location="s3://bucket/results")
    monkeypatch.setattr(fire_ban.time, "monotonic", iter([0, 6]).__next__)
    try:
        adapter.query("snapshot-1", 45.64, -78.62)
    except TimeoutError:
        assert timed.stopped == ["query-1"]
    else:
        raise AssertionError("Athena timeout not raised")
    monkeypatch.undo()
    failed = FakeAthena(["FAILED"])
    adapter = fire_ban.AthenaFireBanQueryAdapter(client=failed, database="db", table="t", output_location="s3://bucket/results")
    try:
        adapter.query("snapshot-1", 45.64, -78.62)
    except RuntimeError as error:
        assert str(error) == "athena_query_failed"
    else:
        raise AssertionError("Athena failure not raised")


def test_athena_rows_reject_incomplete_or_malformed_shapes() -> None:
    valid_header = [{"VarCharValue": column} for column in fire_ban._ATHENA_COLUMNS]
    valid_values = [{"VarCharValue": value} for value in ("p1", "Algonquin", "active", "2026-08-19", "2026-08-20T12:00:00Z", "https://example.invalid", "sha256:test", "Fire ban in effect.")]
    for rows in (
        [{"Data": valid_header}, {"Data": valid_header[:-1]}],
        [{"Data": valid_header}, {"Data": [*valid_header[:-1], "not-a-cell"]}],
        [{"Data": [{"VarCharValue": "park_id"}]}],
        [{"Data": valid_header}, {"Data": [*valid_values[:-1], {"VarCharValue": None}]}],
        [{"Data": valid_header}, {"Data": [*valid_values[:-1], {"VarCharValue": "  "}]}],
    ):
        try:
            fire_ban._athena_rows({"ResultSet": {"Rows": rows}})
        except TypeError:
            pass
        else:
            raise AssertionError("malformed Athena result accepted")


def test_local_lookup_benchmark_reports_only_local_time() -> None:
    snapshot = fire_ban.load_snapshot(FIXTURE)
    durations_ms = []
    for _ in range(1000):
        started = perf_counter()
        fire_ban.lookup(45.64, -78.62, snapshot, now=NOW)
        durations_ms.append((perf_counter() - started) * 1000)
    p50, p95 = quantiles(durations_ms, n=100, method="inclusive")[49], quantiles(durations_ms, n=100, method="inclusive")[94]
    assert p95 < 10
    print(f"stage_9_2_local_lookup_p50_ms={p50:.3f} p95_ms={p95:.3f} cloud_latency=deferred")


def test_weather_continues_when_optional_fire_lookup_fails(monkeypatch) -> None:
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_: [{"temperature_c": 10, "precipitation_probability": 0, "precipitation_mm": 0, "gust_kmh": 5, "weather_code": 1, "time": "2026-08-21T12:00"}])
    monkeypatch.setattr(handler, "_select_weather_period", lambda periods, window: periods[0])
    monkeypatch.setattr(handler, "_trip_guidance", lambda *_: ["Keep normal caution."])
    monkeypatch.setattr(handler, "_lookup_fire_ban", lambda *_: (_ for _ in ()).throw(RuntimeError("query failure")))
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **kwargs: "Weather remains available.")
    context = {"time_window": "today", "activity": "general", "location_text": "", "coordinates": None}
    assert handler._weather_reply("weather and fire ban at 45.64,-78.62", (45.64, -78.62), "coordinates", context) == "Weather remains available."


def test_successful_combined_weather_fire_response_includes_fire_status(monkeypatch) -> None:
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_: [{"temperature_c": 10, "precipitation_probability": 0, "precipitation_mm": 0, "gust_kmh": 5, "weather_code": 1, "time": "2026-08-21T12:00"}])
    monkeypatch.setattr(handler, "_select_weather_period", lambda periods, window: periods[0])
    monkeypatch.setattr(handler, "_trip_guidance", lambda *_: ["Keep normal caution."])
    monkeypatch.setattr(handler, "_lookup_fire_ban", lambda *_: fire_ban.lookup(45.15, -79.35, fire_ban.load_snapshot(FIXTURE), now=NOW))
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **kwargs: "Weather remains available.")
    context = {"time_window": "today", "activity": "general", "location_text": "", "coordinates": None}
    response = handler._weather_reply("weather and fire ban at 45.15,-79.35", (45.15, -79.35), "coordinates", context)
    assert "fire ban active" in response and len(response) <= 160


def test_combined_weather_fire_response_reserves_fire_segment(monkeypatch) -> None:
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_: [{"temperature_c": 10, "precipitation_probability": 0, "precipitation_mm": 0, "gust_kmh": 5, "weather_code": 1, "time": "2026-08-21T12:00"}])
    monkeypatch.setattr(handler, "_select_weather_period", lambda periods, window: periods[0])
    monkeypatch.setattr(handler, "_trip_guidance", lambda *_: ["Keep normal caution."])
    monkeypatch.setattr(handler, "_lookup_fire_ban", lambda *_: fire_ban.lookup(45.15, -79.35, fire_ban.load_snapshot(FIXTURE), now=NOW))
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **kwargs: "A very long advisory. " * 30)
    context = {"time_window": "today", "activity": "general", "location_text": "", "coordinates": None}
    response = handler._weather_reply("weather and fire ban at 45.15,-79.35", (45.15, -79.35), "coordinates", context)
    assert response.startswith("Active Fixture Provincial Park: Ontario Parks fire ban active")
    assert len(response) <= 160


def test_combined_weather_fire_response_keeps_unknown_fire_result(monkeypatch) -> None:
    monkeypatch.setattr(handler, "_fetch_weather", lambda *_: [{"temperature_c": 10, "precipitation_probability": 0, "precipitation_mm": 0, "gust_kmh": 5, "weather_code": 1, "time": "2026-08-21T12:00"}])
    monkeypatch.setattr(handler, "_select_weather_period", lambda periods, window: periods[0])
    monkeypatch.setattr(handler, "_trip_guidance", lambda *_: ["Keep normal caution."])
    unknown = fire_ban.FireBanResult(None, "Ontario Parks", "unknown", None, NOW.isoformat(), "https://www.ontarioparks.ca/alerts", None, "snapshot-1", "fresh", uncertainty="park_not_found", boundary="outside")
    monkeypatch.setattr(handler, "_lookup_fire_ban", lambda *_: unknown)
    monkeypatch.setattr(handler, "_bedrock_converse", lambda **kwargs: "Weather advisory. " * 30)
    context = {"time_window": "today", "activity": "general", "location_text": "", "coordinates": None}
    response = handler._weather_reply("weather and fire ban at 43,-75", (43, -75), "coordinates", context)
    assert response.startswith("Fire status unknown for this point; verify Ontario Parks alerts.")
    assert len(response) <= 160


def test_fire_status_handler_path_uses_resolved_point(monkeypatch) -> None:
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _: LocationResolution(LocationCandidate("Burnt Island Lake", 45.64, -78.62, "lake", "Ontario", "fixture"), "resolved"))
    monkeypatch.setattr(handler, "_lookup_fire_ban", lambda *_: fire_ban.lookup(45.64, -78.62, fire_ban.load_snapshot(FIXTURE), now=NOW))
    result = handler._fire_status_reply("fire status at Burnt Island Lake", {"location_text": "Burnt Island Lake"}, ())
    assert "no Ontario Parks fire-ban record" in result
    assert len(result) <= 160


def test_full_handler_extraction_path_dispatches_fire_status(monkeypatch) -> None:
    monkeypatch.setattr(handler, "_extract_weather_context", lambda *_: {"intent": "fire_status", "location_text": "Burnt Island Lake", "coordinates": None})
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _: LocationResolution(LocationCandidate("Burnt Island Lake", 45.64, -78.62, "lake", "Ontario", "fixture"), "resolved"))
    monkeypatch.setattr(handler, "_lookup_fire_ban", lambda *_: fire_ban.lookup(45.64, -78.62, fire_ban.load_snapshot(FIXTURE), now=NOW))
    assert "no Ontario Parks fire-ban record" in handler._reply_for_message("fire status at Burnt Island Lake")
