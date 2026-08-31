"""Stage 7.2 provider evaluations; live calls are explicit via --eval-mode."""

import json
from pathlib import Path
from typing import Any

import pytest

from backcountry_sms import handler
from tests.evals.reporting import record_operation

FIXTURES = json.loads((Path(__file__).parent / "fixtures/location_provider.json").read_text())


def _candidate(fixture: dict[str, Any]) -> handler.LocationCandidate:
    return handler.LocationCandidate(
        fixture["acceptable_names"][0],
        fixture["latitude"],
        fixture["longitude"],
        "CITY",
        "Ontario CAN",
        "nrcan_geonames",
    )


def _instrument_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    for name, provider in (("nrcan_geonames", "_search_canadian_geonames"), ("amazon_places", "_search_amazon_places")):
        original = getattr(handler, provider)

        def measured(query: str, _original: Any = original, _name: str = name) -> list[handler.LocationCandidate]:
            started = time.perf_counter()
            result = _original(query)
            record_operation(
                _name,
                duration_ms=(time.perf_counter() - started) * 1000,
                input_chars=len(query),
                output_chars=0,
                provider=_name,
                candidate_count=len(result),
                network=_original.__module__ != __name__,
            )
            return result

        monkeypatch.setattr(handler, provider, measured)


@pytest.mark.eval_location
@pytest.mark.parametrize("fixture", FIXTURES, ids=[fixture["id"] for fixture in FIXTURES])
def test_location_provider_contract(
    fixture: dict[str, Any], request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode = request.config.getoption("--eval-mode")
    if mode == "bedrock-live":
        pytest.skip("bedrock-live mode does not run provider evaluations")
    if mode == "offline":
        if fixture["expected_outcome"] == "resolved":
            candidate = _candidate(fixture)
            monkeypatch.setattr(handler, "_search_canadian_geonames", lambda _query: [candidate])
            monkeypatch.setattr(handler, "_search_amazon_places", lambda _query: [])
        elif fixture["expected_outcome"] == "ambiguous":
            candidates = [
                handler.LocationCandidate("Springfield", 45.0, -78.0, "CITY", "Ontario", "nrcan_geonames"),
                handler.LocationCandidate("Springfield", 50.0, -85.0, "CITY", "Ontario", "nrcan_geonames"),
            ]
            monkeypatch.setattr(handler, "_search_canadian_geonames", lambda _query: candidates)
            monkeypatch.setattr(handler, "_search_amazon_places", lambda _query: [])
        else:
            monkeypatch.setattr(handler, "_search_canadian_geonames", lambda _query: [])
            monkeypatch.setattr(handler, "_search_amazon_places", lambda _query: [])
    _instrument_providers(monkeypatch)

    resolution = handler._resolve_named_place(fixture["query"])

    assert resolution.outcome == fixture["expected_outcome"]
    if fixture["expected_outcome"] == "resolved":
        assert resolution.candidate is not None
        assert resolution.candidate.name in fixture["acceptable_names"]
        assert abs(resolution.candidate.latitude - fixture["latitude"]) <= fixture["tolerance"]
        assert abs(resolution.candidate.longitude - fixture["longitude"]) <= fixture["tolerance"]
    else:
        assert resolution.candidate is None


@pytest.mark.eval_location
@pytest.mark.parametrize("fixture", FIXTURES, ids=[fixture["id"] for fixture in FIXTURES])
def test_location_provider_live_mode_is_not_silent(
    fixture: dict[str, Any], request: pytest.FixtureRequest,
) -> None:
    if request.config.getoption("--eval-mode") != "provider-live":
        pytest.skip("requires --eval-mode=provider-live")
    resolution = handler._resolve_named_place(fixture["query"])
    assert resolution.outcome == fixture["expected_outcome"]
    if fixture["expected_outcome"] == "resolved":
        assert resolution.candidate is not None
        assert resolution.candidate.name in fixture["acceptable_names"]
        assert abs(resolution.candidate.latitude - fixture["latitude"]) <= fixture["tolerance"]
        assert abs(resolution.candidate.longitude - fixture["longitude"]) <= fixture["tolerance"]
    else:
        assert resolution.candidate is None
