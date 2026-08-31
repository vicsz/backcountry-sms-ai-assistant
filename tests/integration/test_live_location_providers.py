"""Opt-in checks for real Stage 4 providers; never run in normal unit validation."""

import os

import pytest

from backcountry_sms import handler

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_INTEGRATION") != "1",
        reason="set RUN_LIVE_INTEGRATION=1 to call live providers",
    ),
]


def test_live_coordinate_weather_contract() -> None:
    periods = handler._fetch_weather(45.62, -78.42)

    assert periods and {"temperature_c", "gust_kmh", "time"} <= periods[0].keys()


def test_live_gps_extraction_preserves_exact_coordinates() -> None:
    context = handler._extract_weather_context("weather at 45.62 N, 78.42 W")

    assert context is not None
    assert context["intent"] == "weather"
    assert handler._coordinates_from_context(context) == (45.62, -78.42)


def test_live_nrcan_named_feature_contract() -> None:
    candidates = handler._search_canadian_geonames("Burnt Island Lake, Algonquin")

    assert any(candidate.name == "Burnt Island Lake" for candidate in candidates)
    assert all(-90 <= candidate.latitude <= 90 and -180 <= candidate.longitude <= 180 for candidate in candidates)


def test_live_location_resolution_matrix() -> None:
    assert handler._resolve_named_place("Toronto").candidate is not None
    assert handler._resolve_named_place("Burnt Island Lake, Algonquin").candidate is not None
    assert handler._resolve_named_place("This Place Does Not Exist 998877").candidate is None

    # Portage Store is a POI/business candidate, so it intentionally exercises Amazon Location.
    portage_store = handler._resolve_named_place("Portage Store")
    assert portage_store.candidate is not None


@pytest.mark.parametrize(
    ("message", "expected_location"),
    [
        ("I'm in Toronto now; how are conditions?", "Toronto"),
        ("Will I need a tarp at Burnt Island Lake tomorrow?", "Burnt Island Lake"),
        ("Currently near the Portage Store, forecast tomorrow?", "Portage Store"),
    ],
)
def test_live_bedrock_named_location_extraction_contract(message: str, expected_location: str) -> None:
    context = handler._extract_weather_context(message)

    assert context is not None
    assert set(context) == {
        "intent", "location_text", "current_location_text", "coordinates", "activity", "time_window", "location_source"
    }
    assert context["intent"] == "weather"
    assert context["location_source"] == "current"
    assert context["location_text"] == expected_location
    assert context["current_location_text"] == expected_location


def test_live_bedrock_missing_and_ambiguous_location_contracts() -> None:
    missing = handler._extract_weather_context("What's the weather?")
    ambiguous = handler._extract_weather_context("Springfield weather")

    assert missing is not None
    assert missing["intent"] in {"weather", "unclear"}
    assert missing["location_text"] == ""
    assert missing["current_location_text"] == ""
    assert missing["coordinates"] is None
    assert ambiguous is not None
    assert ambiguous["intent"] in {"weather", "unclear"}
    assert ambiguous["coordinates"] is None
    if ambiguous["intent"] == "weather":
        assert ambiguous["location_source"] == "current"
        assert ambiguous["location_text"]


def test_live_current_location_overrides_history_contract() -> None:
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old response", "public-example")]

    context = handler._extract_weather_context("I'm in Toronto now; how are conditions?", history)

    assert context is not None
    assert context["intent"] == "weather"
    assert context["location_text"] == "Toronto"
    assert context["current_location_text"] == "Toronto"
    assert context["location_source"] == "current"


def test_live_current_location_response_has_no_historical_name_and_is_bounded() -> None:
    history = [handler.ContextInteraction("Weather at Pine Ridge", "old response", "public-example")]

    response = handler._reply_for_message("I'm in Toronto now; how are conditions?", history)

    assert response
    assert "Pine Ridge" not in response
    assert sum(2 if char in handler.GSM_EXTENDED else 1 for char in response) <= 160


def test_live_response_rejects_single_word_historical_location_leakage() -> None:
    history = [handler.ContextInteraction("Weather at Toronto", "old response", "public-example")]

    response = handler._reply_for_message("I'm at Burnt Island Lake now; how are conditions?", history)

    assert response
    assert "Toronto" not in response
    assert sum(2 if char in handler.GSM_EXTENDED else 1 for char in response) <= 160


def test_live_clarification_response_is_bounded_to_one_sms_segment() -> None:
    response = handler._clarification_reply("Can you help?", ())

    assert response
    assert sum(2 if char in handler.GSM_EXTENDED else 1 for char in response) <= 160
