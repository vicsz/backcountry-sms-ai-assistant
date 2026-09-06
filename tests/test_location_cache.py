"""Unit coverage for the bounded successful-location cache."""

from backcountry_sms import location


def _candidate() -> location.LocationCandidate:
    return location.LocationCandidate("Toronto", 43.65, -79.38, "CITY", "Ontario", "nrcan_geonames")


def test_successful_resolution_is_cached_and_query_is_normalized(monkeypatch) -> None:
    calls = []
    candidate = _candidate()
    monkeypatch.setattr(location, "search_canadian_geonames", lambda query: (calls.append(query) or [candidate]))
    location.clear_location_cache()

    first = location.resolve_named_place(" Toronto ")
    second = location.resolve_named_place("toronto")

    assert first == second
    assert calls == [" Toronto "]


def test_failed_resolution_is_not_cached(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(location, "search_canadian_geonames", lambda query: (calls.append(query) or []))
    monkeypatch.setattr(location, "search_amazon_places", lambda query: [])
    location.clear_location_cache()

    first = location.resolve_named_place("Unknown place")
    second = location.resolve_named_place("Unknown place")

    assert first.outcome == second.outcome == "not_found"
    assert calls == ["Unknown place", "Unknown place"]


def test_cache_evicts_oldest_entry(monkeypatch) -> None:
    candidates = {
        "one": location.LocationCandidate("One", 43.0, -79.0, "CITY", "Ontario", "nrcan_geonames"),
        "two": location.LocationCandidate("Two", 44.0, -80.0, "CITY", "Ontario", "nrcan_geonames"),
    }
    calls = []
    monkeypatch.setenv("LOCATION_CACHE_MAX_ENTRIES", "1")
    monkeypatch.setattr(location, "search_canadian_geonames", lambda query: (calls.append(query) or [candidates[query]]))
    location.clear_location_cache()

    location.resolve_named_place("one")
    location.resolve_named_place("two")
    location.resolve_named_place("one")

    assert calls == ["one", "two", "one"]
