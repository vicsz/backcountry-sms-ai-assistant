"""Provider-backed named-place resolution. Providers are the sole coordinate authority."""

import json
import logging
import os
import re
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import boto3

from .models import (
    GEONAMES_API_URL,
    GEONAMES_TIMEOUT_SECONDS,
    LOCATION_TIMEOUT_SECONDS,
    LocationCandidate,
    LocationResolution,
)
from .telemetry import emit_event
from .tracing import trace_span

LOGGER = logging.getLogger(__name__)
_LOCATION_CACHE: OrderedDict[str, LocationResolution] = OrderedDict()
_DEFAULT_LOCATION_CACHE_MAX_ENTRIES = 128


def _location_cache_max_entries() -> int:
    try:
        configured = int(os.getenv("LOCATION_CACHE_MAX_ENTRIES", str(_DEFAULT_LOCATION_CACHE_MAX_ENTRIES)))
    except ValueError:
        configured = _DEFAULT_LOCATION_CACHE_MAX_ENTRIES
    return max(1, min(configured, 1024))


def clear_location_cache() -> None:
    """Clear the process-local cache; used by tests and controlled experiments."""
    _LOCATION_CACHE.clear()


def _location_cache_key(place_query: str) -> str:
    return place_query.strip().casefold()


def resolve_named_place(place_query: str) -> LocationResolution:
    """Resolve a named place, reusing only successful provider-verified results."""
    cache_key = _location_cache_key(place_query)
    with trace_span("location.cache", provider="location"):
        cached = _LOCATION_CACHE.get(cache_key)
        if cached is not None:
            _LOCATION_CACHE.move_to_end(cache_key)
            emit_event("location_cache", "hit", metrics={"LocationCacheHits": 1})
            return cached
        emit_event("location_cache", "miss", metrics={"LocationCacheMisses": 1})

    resolution = _resolve_named_place_uncached(place_query)
    if resolution.outcome == "resolved" and resolution.candidate is not None:
        _LOCATION_CACHE[cache_key] = resolution
        _LOCATION_CACHE.move_to_end(cache_key)
        while len(_LOCATION_CACHE) > _location_cache_max_entries():
            _LOCATION_CACHE.popitem(last=False)
    return resolution


def _resolve_named_place_uncached(place_query: str) -> LocationResolution:
    """Use provider candidates only; Canada/Ontario is a ranking bias, never a guessed point."""
    try:
        with trace_span("location.lookup", provider="nrcan_geonames"):
            canadian_candidates = search_canadian_geonames(place_query)
    except Exception as error:  # noqa: BLE001
        LOGGER.info("location_provider_failed provider=nrcan_geonames error_type=%s", type(error).__name__)
        canadian_candidates, canadian_failed = [], True
    else:
        canadian_failed = False
    if canadian_candidates:
        LOGGER.info("location_candidates_found source=nrcan_geonames")
        canadian_resolution = rank_location_candidates(place_query, canadian_candidates)
        if canadian_resolution.candidate is not None:
            emit_event("location_resolved", "success", provider="nrcan", metrics={"LocationResolutions": 1})
            return canadian_resolution
    try:
        with trace_span("location.lookup", provider="amazon_places"):
            amazon_candidates = search_amazon_places(place_query)
    except Exception as error:  # noqa: BLE001
        LOGGER.info("location_provider_failed provider=amazon_location_places error_type=%s", type(error).__name__)
        amazon_candidates, amazon_failed = [], True
    else:
        amazon_failed = False
    candidates = canadian_candidates + amazon_candidates
    if not candidates:
        outcome = "unavailable" if canadian_failed and amazon_failed else "not_found"
        emit_event("location_failed", "failure", provider="amazon_places", outcome=outcome, metrics={"LocationFailures": 1})
        return LocationResolution(None, outcome)
    LOGGER.info("location_candidates_found source=amazon_location_places")
    resolution = rank_location_candidates(place_query, candidates)
    emit_event("location_resolved" if resolution.candidate else "location_failed", "success" if resolution.candidate else "failure", provider="amazon_places", outcome=resolution.outcome, metrics={"LocationResolutions" if resolution.candidate else "LocationFailures": 1})
    return resolution


def search_canadian_geonames(place_query: str) -> list[LocationCandidate]:
    payload = get_json(GEONAMES_API_URL, {"q": provider_query(place_query), "province": "35", "category": "O"}, GEONAMES_TIMEOUT_SECONDS)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("features"), list):
        raise TypeError("invalid_geonames_response")
    candidates: list[LocationCandidate] = []
    for feature in payload["features"][:10]:
        if not isinstance(feature, Mapping) or not isinstance(feature.get("properties"), Mapping):
            continue
        properties, point = feature["properties"], geometry_point(feature.get("geometry"))
        name = properties.get("name")
        if point is None or not isinstance(name, str):
            continue
        candidate = validated_candidate(name=name, latitude=point[0], longitude=point[1], feature_type=str(properties.get("concise", "")), region=str(properties.get("location", "Ontario")), source="nrcan_geonames", score=provider_score(properties.get("relevance")))
        if candidate is not None:
            candidates.append(candidate)
    return candidates


@lru_cache(maxsize=1)
def _amazon_places_client() -> Any:
    with trace_span("client.init", provider="amazon_places"):
        return boto3.client("geo-places", config=location_client_config())


def search_amazon_places(place_query: str) -> list[LocationCandidate]:
    response = _amazon_places_client().search_text(
        QueryText=place_query, Filter={"IncludeCountries": ["CAN", "USA"]}, BiasPosition=[-84.0, 49.0], MaxResults=5, IntendedUse="SingleUse", Language="en"
    )
    items = response.get("ResultItems") if isinstance(response, Mapping) else None
    if not isinstance(items, list):
        raise TypeError("invalid_amazon_places_response")
    candidates: list[LocationCandidate] = []
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("Address"), Mapping):
            continue
        address = item["Address"]
        position, label = item.get("Position"), item.get("Title")
        if not isinstance(position, Sequence) or len(position) != 2 or not isinstance(label, str):
            continue
        categories = item.get("Categories", [])
        candidate = validated_candidate(name=label, latitude=position[1], longitude=position[0], feature_type=",".join(category_name(value) for value in categories if category_name(value)), region=amazon_region(address), source="amazon_location_places", score=0.0)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def location_client_config() -> Any:
    from botocore.config import Config
    return Config(connect_timeout=LOCATION_TIMEOUT_SECONDS, read_timeout=LOCATION_TIMEOUT_SECONDS, retries={"mode": "standard", "max_attempts": 3})


def get_json(url: str, query: Mapping[str, str], timeout: int) -> object:
    with urlopen(f"{url}?{urlencode(query)}", timeout=timeout) as response:
        return json.loads(response.read(262144).decode("utf-8"))


def provider_query(place_query: str) -> str:
    return place_query.split(",", maxsplit=1)[0].strip()


def geometry_point(geometry: object) -> tuple[float, float] | None:
    if not isinstance(geometry, Mapping):
        return None
    pairs = list(coordinate_pairs(geometry.get("coordinates")))
    if not pairs:
        return None
    longitudes, latitudes = zip(*pairs, strict=True)
    return ((min(latitudes) + max(latitudes)) / 2, (min(longitudes) + max(longitudes)) / 2)


def coordinate_pairs(value: object) -> list[tuple[float, float]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) == 2 and all(isinstance(item, (int, float)) for item in value):
            return [(float(value[0]), float(value[1]))]
        pairs: list[tuple[float, float]] = []
        for child in value:
            pairs.extend(coordinate_pairs(child))
        return pairs
    return []


def amazon_region(address: object) -> str:
    if not isinstance(address, Mapping):
        return ""
    return " ".join(address_name(address.get(key)) for key in ("Locality", "SubRegion", "Region", "Country") if address_name(address.get(key)))


def address_name(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("Name", value.get("Code3", "")))
    return str(value) if value else ""


def category_name(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("Name", value.get("Id", "")))
    return str(value) if isinstance(value, str) else ""


def provider_score(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def validated_candidate(**kwargs: object) -> LocationCandidate | None:
    try:
        latitude_value, longitude_value = kwargs["latitude"], kwargs["longitude"]
        if not isinstance(latitude_value, (int, float, str)) or not isinstance(longitude_value, (int, float, str)):
            return None
        latitude, longitude = float(latitude_value), float(longitude_value)
    except (KeyError, TypeError, ValueError):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return LocationCandidate(**kwargs)  # type: ignore[arg-type]


def rank_location_candidates(place_query: str, candidates: list[LocationCandidate]) -> LocationResolution:
    query = provider_query(place_query).casefold()
    exact = [candidate for candidate in candidates if candidate.name.casefold() == query]
    matches = exact or [candidate for candidate in candidates if _candidate_matches_query(candidate, query)]
    if not matches:
        return LocationResolution(None, "not_found")
    ranked = sorted(matches, key=lambda candidate: (candidate_rank(candidate, query), candidate.score), reverse=True)
    top = ranked[0]
    top_rank = candidate_rank(top, query)
    second_rank = candidate_rank(ranked[1], query) if len(ranked) > 1 else -1
    distinctive_feature = any(token in top.feature_type.casefold() for token in ("lake", "water", "park", "point", "poi", "store"))
    score_separates = (
        len(ranked) > 1
        and distinctive_feature
        and top.score > 0
        and top.score >= ranked[1].score * 2
    )
    if top_rank < 3 or (second_rank == top_rank and far_apart(top, ranked[1]) and not score_separates):
        return LocationResolution(None, "ambiguous")
    return LocationResolution(top, "resolved")


def candidate_rank(candidate: LocationCandidate, query: str) -> int:
    rank = 0
    if candidate.name.casefold() == query or _candidate_matches_query(candidate, query): rank += 3
    # The Canadian provider is queried first with an Ontario filter. Keep the
    # same preference when Amazon Places is needed as a fallback, while still
    # letting provider relevance/popularity decide between equivalent matches.
    if candidate.source == "nrcan_geonames": rank += 1
    if re.search(r"\b(?:can|canada)\b", candidate.region, re.IGNORECASE): rank += 1
    if "ontario" in candidate.region.casefold() or candidate.source == "nrcan_geonames": rank += 1
    if any(token in candidate.feature_type.casefold() for token in ("lake", "water", "park", "point", "poi", "store")): rank += 1
    return rank


def _candidate_matches_query(candidate: LocationCandidate, query: str) -> bool:
    name = candidate.name.casefold()
    if query in name:
        return True
    head = name.split(",", maxsplit=1)[0]
    tokens = re.findall(r"[a-z0-9]+", head)
    return len(query) >= 2 and "".join(token[0] for token in tokens) == query


def far_apart(first: LocationCandidate, second: LocationCandidate) -> bool:
    return abs(first.latitude - second.latitude) > 0.2 or abs(first.longitude - second.longitude) > 0.2
