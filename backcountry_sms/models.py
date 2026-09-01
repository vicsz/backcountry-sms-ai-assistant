"""Shared constants and value objects for the Backcountry SMS assistant."""

from dataclasses import dataclass

DEFAULT_MODEL_ID = "us.amazon.nova-2-lite-v1:0"
NOVA_MICRO_MODEL_ID = "us.amazon.nova-micro-v1:0"
NOVA_MICRO_SUPPORTED_REGIONS = ("us-east-1", "us-east-2", "us-west-2")
ALLOWED_MODEL_IDS = (DEFAULT_MODEL_ID, NOVA_MICRO_MODEL_ID)
CONTEXT_HISTORY_LIMIT = 5
CONTEXT_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_SMS_SEPTETS = 160
# Compatibility name for the original Stage 2 test/contract.
MAX_SMS_CHARS = MAX_SMS_SEPTETS
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
GEONAMES_API_URL = "https://geogratis.gc.ca/services/geoname/en/geonames"
GEONAMES_TIMEOUT_SECONDS = 3
LOCATION_TIMEOUT_SECONDS = 3
FAILURE_MESSAGES = {
    "account_verification": "AWS is still verifying AI access. Please try again later.",
    "access_denied": "AI access is not available yet. Please try again later.",
    "throttled": "The AI service is busy. Please try again shortly.",
    "timeout": "The AI service took too long to respond. Please try again.",
    "service_unavailable": "The AI service is temporarily unavailable. Please try again.",
    "malformed_output": "The AI service returned an invalid response. Please try again.",
    "unknown": "The AI assistant is temporarily unavailable. Please try again.",
}
WEATHER_LOCATION_PROMPT = "Please include GPS coordinates or a named place, for example: weather at 45.62,-78.42."
WEATHER_COORDINATE_FALLBACK = "Those coordinates need correction. Please send latitude and longitude, e.g. 45.62,-78.42."
WEATHER_LOCATION_NOT_FOUND = "I couldn't verify that place. Please send GPS coordinates or more location detail."
WEATHER_LOCATION_AMBIGUOUS = "That place is ambiguous. Please send GPS coordinates or add a nearby park or town."
WEATHER_LOCATION_UNAVAILABLE = "Location lookup is unavailable right now. Please try GPS coordinates later."
WEATHER_EXTRACTION_FALLBACK = "I couldn't understand that weather request. Please include GPS coordinates or a named place."
WEATHER_PROVIDER_FALLBACK = "Weather data is unavailable right now. Please try again shortly."
WEATHER_ADVICE_FALLBACK = "Weather is available, but advice is unavailable. Please use caution."
CURRENT_DATA_LIMITATION_REPLY = "I don't have real-time news or stats. I can provide weather, fire status, and Ontario Parks guide information."
FALLBACK_REPLY = FAILURE_MESSAGES["unknown"]

COORDINATE_NUMBER = r"[+-]?\d{1,3}(?:\.\d+)?"

@dataclass(frozen=True)
class LocationCandidate:
    """A coordinate-bearing result returned by one approved location provider."""

    name: str
    latitude: float
    longitude: float
    feature_type: str
    region: str
    source: str
    score: float = 0.0

@dataclass(frozen=True)
class LocationResolution:
    candidate: LocationCandidate | None
    outcome: str

@dataclass(frozen=True)
class ContextInteraction:
    """One unexpired, user-scoped prior accepted SMS exchange."""

    input_body: str
    output_body: str
    created_at: str
