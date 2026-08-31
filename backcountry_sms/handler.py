"""Lambda entrypoint and bounded SMS orchestration.

The entrypoint retains the original private helper names as a compatibility surface.
Provider, persistence, and model details live in focused modules.
"""

import json
import logging
import os
import re
import time
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any, cast
from urllib.request import urlopen

import boto3
from botocore.config import Config

from . import bedrock, context_store, fire_ban, location, models, retrieval, weather
from .bedrock import (
    ADVICE_SYSTEM_PROMPT,
    CLARIFICATION_SYSTEM_PROMPT,
    COORDINATE_CORRECTION_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
    GENERAL_SYSTEM_PROMPT,
    LOCATION_REQUEST_SYSTEM_PROMPT,
    RAG_SYSTEM_PROMPT,
    WEATHER_UNAVAILABLE_SYSTEM_PROMPT,
)
from .models import (
    DEFAULT_MODEL_ID,  # noqa: F401 - compatibility export
    FAILURE_MESSAGES,
    FALLBACK_REPLY,
    GEONAMES_API_URL,  # noqa: F401 - compatibility export
    MAX_SMS_CHARS,
    WEATHER_ADVICE_FALLBACK,
    WEATHER_COORDINATE_FALLBACK,
    WEATHER_EXTRACTION_FALLBACK,
    WEATHER_LOCATION_AMBIGUOUS,
    WEATHER_LOCATION_NOT_FOUND,
    WEATHER_LOCATION_PROMPT,
    WEATHER_LOCATION_UNAVAILABLE,
    WEATHER_PROVIDER_FALLBACK,
    ContextInteraction,
    LocationCandidate,
    LocationResolution,
)
from .telemetry import emit_event
from .tracing import trace_span

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
_COLD_START = True
INTERPRETATION_SCHEMA_KEYS = {
    "intent",
    "location_text",
    "current_location_text",
    "coordinates",
    "time_window",
    "activity",
    "location_source",
}
# Compatibility exports retained for callers of the original monolithic module.
CONTEXT_HISTORY_LIMIT = models.CONTEXT_HISTORY_LIMIT
CONTEXT_TTL_SECONDS = models.CONTEXT_TTL_SECONDS
MAX_SMS_SEPTETS = models.MAX_SMS_SEPTETS
WEATHER_API_URL = models.WEATHER_API_URL
GEONAMES_TIMEOUT_SECONDS = models.GEONAMES_TIMEOUT_SECONDS
LOCATION_TIMEOUT_SECONDS = models.LOCATION_TIMEOUT_SECONDS
COORDINATE_NUMBER = models.COORDINATE_NUMBER
RAG_LAMBDA_TIMEOUT_SECONDS = 25
RAG_OPERATION_OVERHEAD_SECONDS = 2
RAG_EXTRACTION_TIMEOUT_SECONDS = bedrock.RAG_BEDROCK_CONNECT_TIMEOUT_SECONDS + bedrock.RAG_BEDROCK_READ_TIMEOUT_SECONDS
RAG_RETRIEVAL_TIMEOUT_SECONDS = retrieval.RAG_RETRIEVAL_CONNECT_TIMEOUT_SECONDS + retrieval.RAG_RETRIEVAL_READ_TIMEOUT_SECONDS
RAG_RESPONSE_TIMEOUT_SECONDS = bedrock.RAG_BEDROCK_CONNECT_TIMEOUT_SECONDS + bedrock.RAG_BEDROCK_READ_TIMEOUT_SECONDS
RAG_WORST_CASE_SECONDS = (
    RAG_EXTRACTION_TIMEOUT_SECONDS
    + RAG_RETRIEVAL_TIMEOUT_SECONDS
    + RAG_RESPONSE_TIMEOUT_SECONDS
    + RAG_OPERATION_OVERHEAD_SECONDS
)
assert RAG_WORST_CASE_SECONDS <= RAG_LAMBDA_TIMEOUT_SECONDS
GSM_BASIC = bedrock.GSM_BASIC
GSM_EXTENDED = bedrock.GSM_EXTENDED
CHARACTER_REPLACEMENTS = bedrock.CHARACTER_REPLACEMENTS
_LOCATION_GEONAMES_PROVIDER = location.search_canadian_geonames
_LOCATION_AMAZON_PROVIDER = location.search_amazon_places
COORDINATE_PATTERN = re.compile(
    r"(?:\b(?:lat(?:itude)?|y)\s*[:=]?\s*)?(?P<latitude>[+-]?\d{1,3}(?:\.\d+)?)\s*(?:°|º)?\s*(?P<latitude_hemisphere>[NS])?\s*(?:,|/|;|\s+)\s*(?:\b(?:lon(?:gitude)?|lng|x)\s*[:=]?\s*)?(?P<longitude>[+-]?\d{1,3}(?:\.\d+)?)\s*(?:°|º)?\s*(?P<longitude_hemisphere>[EW])?\b",
    re.IGNORECASE,
)


def lambda_handler(event: Mapping[str, Any], _context: object) -> dict[str, str]:
    global _COLD_START
    cold_start = _COLD_START
    _COLD_START = False
    started = time.perf_counter()
    message = _extract_message(event)
    if message is None:
        LOGGER.info("sms_event_ignored reason=unsupported_event")
        emit_event("sms_ignored", "ignored", outcome="unsupported_event", metrics={"MessagesIgnored": 1})
        return {"status": "ignored", "reason": "unsupported_event"}
    sender = message.get("originationNumber")
    user_phone = _normalized_e164(sender)
    allowed_sender = os.environ.get("ALLOWED_PHONE_NUMBER")
    if sender != allowed_sender and (not user_phone or user_phone != _normalized_e164(allowed_sender)):
        LOGGER.info("sms_event_ignored reason=sender_not_allowed")
        emit_event("sms_ignored", "ignored", outcome="sender_not_allowed", metrics={"MessagesIgnored": 1})
        return {"status": "ignored", "reason": "sender_not_allowed"}
    delivery_mode = _delivery_mode()
    message_id = message.get("_sns_message_id")
    created_at = _context_created_at(message.get("_sns_timestamp"), message_id)
    context_phone = user_phone or (sender if isinstance(sender, str) else "")
    history, readable = _load_context(context_phone)
    body = message.get("messageBody", "")
    reserved = _reserve_interaction(context_phone, str(message_id or ""), created_at, body)
    if reserved is None:
        LOGGER.info("sms_event_failed reason=storage_unavailable")
        emit_event("sms_ignored", "failure", outcome="storage_unavailable")
        return {"status": "failed", "reason": "storage_unavailable"}
    if not reserved:
        LOGGER.info("sms_event_ignored reason=duplicate_delivery")
        emit_event("sms_ignored", "ignored", outcome="duplicate_delivery", metrics={"MessagesIgnored": 1})
        return {"status": "ignored", "reason": "duplicate_delivery"}
    response_text = _reply_for_message(body, history, readable)
    if delivery_mode == "capture":
        _log_captured_response(str(message_id or ""), response_text)
    else:
        try:
            with trace_span("sms.send", provider="end_user_messaging"):
                _sms_client().send_text_message(
                    DestinationPhoneNumber=sender, OriginationIdentity=os.environ["ORIGINATION_IDENTITY"],
                    MessageBody=response_text, MessageType="TRANSACTIONAL",
                )
        except Exception as error:  # noqa: BLE001
            LOGGER.info("sms_send_failed error_type=%s", type(error).__name__)
            emit_event("sms_send_failed", "failure", outcome="sms_send_failed", metrics={"SmsSendFailures": 1})
            return {"status": "failed", "reason": "sms_send_failed"}
    _complete_interaction(context_phone, str(message_id or ""), created_at, body, response_text)
    LOGGER.info("sms_event_replied" if delivery_mode == "live" else "sms_event_captured")
    duration_ms = (time.perf_counter() - started) * 1000
    emit_event("sms_replied", "success", duration_ms=duration_ms, metrics={"MessagesReceived": 1, "RepliesSent": 1, "ProcessingDurationMs": duration_ms, "ColdStarts": int(cold_start)})
    if delivery_mode == "capture":
        return {"status": "captured", "delivery_mode": delivery_mode, "sms_api_called": "false", "sns_published": "false"}
    return {"status": "replied"}


def _delivery_mode() -> str:
    """Return the explicit outbound policy and fail closed outside a test target."""
    test_mode_value = os.environ.get("TEST_MODE", "false").strip().lower()
    if test_mode_value not in {"true", "false"}:
        raise RuntimeError("invalid_test_mode")
    test_mode = test_mode_value == "true"
    mode = os.environ.get("SMS_DELIVERY_MODE", "live").strip().lower()
    deployment_environment = os.environ.get("DEPLOYMENT_ENVIRONMENT", "production").strip().lower()
    if mode not in {"capture", "live"} or deployment_environment not in {"production", "test"}:
        raise RuntimeError("invalid_sms_delivery_mode")
    if mode == "capture" and (not test_mode or deployment_environment != "test"):
        raise RuntimeError("capture_mode_not_permitted")
    if test_mode and mode != "capture":
        raise RuntimeError("test_mode_requires_capture")
    return mode


def _log_captured_response(test_run_id: str, response_text: str) -> None:
    """Log synthetic-test output only; never include sender or destination identifiers."""
    LOGGER.info(json.dumps({
        "event": "test_response_captured",
        "test_run_id": test_run_id,
        "delivery_mode": "capture",
        "response": response_text,
        "sms_api_called": False,
        "sns_published": False,
    }, separators=(",", ":")))


def _reply_for_message(user_text: object, history: Sequence[ContextInteraction] = (), context_readable: bool = True) -> str:
    text = user_text if isinstance(user_text, str) else ""
    redirect = _current_status_redirect(text)
    if redirect is not None:
        return redirect
    context = _extract_weather_context(text, history)
    if context is None:
        LOGGER.info("message_interpretation_failed")
        return _interpretation_fallback()
    intent = context["intent"]
    # The model can classify a live question as guide information. These
    # deterministic lexical boundaries keep weather and fire questions off RAG.
    if _contains_weather_term(text):
        intent = "weather"
    elif _contains_fire_term(text):
        intent = "fire_status"
    if intent == "fire_status":
        return _fire_status_reply(text, context, history)
    if intent == "weather":
        coordinates = _parse_coordinates(text)
        if _contains_coordinate_attempt(text) and coordinates is None:
            LOGGER.info("coordinate_invalid")
            return _coordinate_correction_reply(text, history)
        return _weather_request_reply(text, coordinates, history, context_readable, context)
    if intent == "information_lookup":
        return _information_lookup_reply(text)
    if intent == "unclear":
        return _clarification_reply(text, history)
    return _bedrock_reply(text, history)


def _extract_message(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    records = event.get("Records")
    if not isinstance(records, list) or not records:
        return None
    sns_record = records[0].get("Sns") if isinstance(records[0], Mapping) else None
    raw_message = sns_record.get("Message") if isinstance(sns_record, Mapping) else None
    if not isinstance(raw_message, str):
        return None
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError:
        return None
    if not isinstance(message, Mapping):
        return None
    sns_mapping = cast(Mapping[str, Any], sns_record)
    return {**message, "_sns_message_id": sns_mapping.get("MessageId", ""), "_sns_timestamp": sns_mapping.get("Timestamp", "")}


def _weather_request_reply(user_text: str, current_coordinates: tuple[float, float] | None, history: Sequence[ContextInteraction], context_readable: bool, context: dict[str, object]) -> str:
    if current_coordinates is not None:
        model_coordinates = _coordinates_from_context(context)
        if model_coordinates is not None and model_coordinates != current_coordinates:
            LOGGER.info("weather_coordinates_conflict")
            return _coordinate_correction_reply(user_text, history)
        return _weather_reply(user_text, current_coordinates, "coordinates", context, history, "provided GPS coordinates")
    if context["coordinates"] is not None:
        # The model may normalize coordinates visible in the current SMS, but it
        # is never a coordinate authority. Without an exact parsed input, reject
        # its point instead of silently moving the user to a model-supplied one.
        LOGGER.info("weather_model_coordinates_rejected")
        if not context["location_text"]:
            return _coordinate_correction_reply(user_text, history)
    if not context_readable and context["location_source"] == "history":
        LOGGER.info("weather_request_missing_location")
        return _location_request_reply(user_text, history)
    if not context["location_text"]:
        LOGGER.info("weather_request_missing_location")
        return _location_request_reply(user_text, history)
    return _named_weather_reply(user_text, context, history)


def _weather_reply(user_text: str, coordinates: tuple[float, float], location_source: str, context: dict[str, object] | None = None, history: Sequence[ContextInteraction] = (), verified_location_label: str = "") -> str:
    context = context or _extract_weather_context(user_text, history)
    if context is None:
        LOGGER.info("weather_request_extraction_failed")
        return WEATHER_EXTRACTION_FALLBACK
    try:
        forecast = _fetch_weather(*coordinates)
        selected = _select_weather_period(forecast, str(context["time_window"]))
    except Exception as error:  # noqa: BLE001
        LOGGER.info("weather_provider_failed error_type=%s", type(error).__name__)
        return _weather_unavailable_reply(user_text, history)
    fire_result = None
    if _fire_requested(user_text):
        try:
            fire_result = _lookup_fire_ban(*coordinates)
        except Exception as error:  # noqa: BLE001
            LOGGER.info("fire_ban_lookup_failed error_type=%s", type(error).__name__)
    activity, time_window = str(context["activity"]), str(context["time_window"])
    guidance = _trip_guidance(selected, activity)
    LOGGER.info("weather_request_parsed")
    LOGGER.info("location_resolved source=%s", location_source)
    try:
        advice_input = {
            "inbound_sms": user_text,
            "location": {"label": verified_location_label, "coordinates": {"latitude": coordinates[0], "longitude": coordinates[1]}},
            "weather": selected,
            "guidance": guidance,
            "activity": activity,
            "time_window": time_window,
            "fire_ban": fire_result.__dict__ if fire_result is not None else None,
        }
        advice = _bedrock_converse(system_prompt=ADVICE_SYSTEM_PROMPT, user_text=json.dumps(advice_input, separators=(",", ":")), max_tokens=96, temperature=0.2, history=history)
    except Exception as error:  # noqa: BLE001
        LOGGER.info("weather_advice_failed error_type=%s", type(error).__name__)
        advice = _deterministic_weather_summary(selected, guidance)
    if _contains_stale_historical_location(advice, history, verified_location_label):
        LOGGER.info("weather_advice_stale_location_rejected")
        advice = _deterministic_weather_summary(selected, guidance)
    if fire_result is not None:
        # Reserve the deterministic fire segment before bounding weather prose so the
        # authoritative successful/unknown result cannot be truncated away.
        fire_segment = fire_ban.format_sms(fire_result)
        if len(fire_segment) > MAX_SMS_CHARS:
            fire_segment = "Fire status unknown; verify Ontario Parks alerts."
        weather_budget = MAX_SMS_CHARS - len(fire_segment) - 1
        weather_text = advice[:max(0, weather_budget)].rstrip()
        advice = f"{fire_segment} {weather_text}".strip()
    LOGGER.info("sms_output_bounded")
    return _bound_sms(advice, WEATHER_ADVICE_FALLBACK)


def _named_weather_reply(user_text: str, context: dict[str, object], history: Sequence[ContextInteraction] = ()) -> str:
    place_query = context["location_text"]
    place_query = cast(str | None, context["location_text"])
    if not place_query:
        return WEATHER_LOCATION_PROMPT
    resolution = _resolve_named_place(place_query)
    if resolution.candidate is None:
        LOGGER.info("location_%s", resolution.outcome)
        fallback = {"not_found": WEATHER_LOCATION_NOT_FOUND, "ambiguous": WEATHER_LOCATION_AMBIGUOUS, "unavailable": WEATHER_LOCATION_UNAVAILABLE}[resolution.outcome]
        return _location_request_reply(user_text, history, fallback)
    candidate = resolution.candidate
    return _weather_reply(user_text, (candidate.latitude, candidate.longitude), candidate.source, context, history, candidate.name)


def _fire_status_reply(user_text: str, context: dict[str, object], history: Sequence[ContextInteraction]) -> str:
    coordinates = _parse_coordinates(user_text)
    label = ""
    if coordinates is None:
        location_text = cast(str, context.get("location_text") or "")
        if not location_text:
            return _location_request_reply(user_text, history, "Please send GPS coordinates or a named Ontario park.")
        resolution = _resolve_named_place(location_text)
        if resolution.candidate is None:
            return _location_request_reply(user_text, history, "I couldn't verify that park. Please send GPS coordinates or a named park.")
        candidate = resolution.candidate
        coordinates, label = (candidate.latitude, candidate.longitude), candidate.name
    try:
        result = _lookup_fire_ban(*coordinates)
    except Exception as error:  # noqa: BLE001
        LOGGER.info("fire_ban_lookup_failed error_type=%s", type(error).__name__)
        result = fire_ban.FireBanResult(label or None, "Ontario Parks", "unknown", None, None, "https://www.ontarioparks.ca/alerts", None, None, "missing", uncertainty="query_failure", boundary="invalid")
    if label and result.park_name is None:
        result = fire_ban.FireBanResult(label, result.jurisdiction, result.status, result.source_as_of, result.retrieved_at, result.source_url, result.source_hash, result.snapshot_id, result.freshness, result.raw_wording, result.uncertainty, result.boundary)
    return _bound_sms(fire_ban.format_sms(result), "Fire status is unknown; verify Ontario Parks alerts.")


def _extract_weather_context(user_text: str, history: Sequence[ContextInteraction] = ()) -> dict[str, object] | None:
    try:
        output = _bedrock_converse(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_text=user_text,
            max_tokens=80,
            temperature=0.0,
            history=history,
            prioritize_current=True,
            operation_budget="rag",
        )
    except Exception as error:  # noqa: BLE001
        LOGGER.info("weather_extraction_failed error_type=%s", type(error).__name__)
        return None
    parsed = _embedded_json_object(output)
    if parsed is None:
        LOGGER.info("weather_extraction_malformed")
        return None
    if set(parsed) != INTERPRETATION_SCHEMA_KEYS:
        LOGGER.info("weather_extraction_invalid_schema_keys")
        return None
    intent = parsed["intent"]
    if intent not in {"weather", "fire_status", "information_lookup", "general", "unclear"}:
        LOGGER.info("weather_extraction_invalid_intent")
        return None
    location_text = parsed["location_text"]
    if location_text is not None and not isinstance(location_text, str):
        LOGGER.info("weather_extraction_invalid_location_text")
        return None
    current_location_text = parsed["current_location_text"]
    if not isinstance(current_location_text, str):
        LOGGER.info("weather_extraction_invalid_current_location_text")
        return None
    location_source = parsed["location_source"]
    if location_source not in {"current", "history", "none"}:
        LOGGER.info("weather_extraction_invalid_location_source")
        return None
    coordinates = parsed["coordinates"]
    if coordinates is not None and not isinstance(coordinates, Mapping):
        LOGGER.info("weather_extraction_invalid_coordinates")
        return None
    if coordinates is not None and _coordinates_from_context({"coordinates": coordinates}) is None:
        LOGGER.info("weather_extraction_invalid_coordinates")
        return None
    time_window = parsed["time_window"]
    activity = parsed["activity"]
    if intent == "weather":
        # Nova occasionally emits null for optional weather qualifiers even
        # though the extraction schema asks for strings. Apply safe defaults,
        # then let explicit wording in the SMS win over the model.
        if (time_window is not None and not isinstance(time_window, str)) or (activity is not None and not isinstance(activity, str)):
            LOGGER.info("weather_extraction_invalid_text_field")
            return None
        time_window = time_window if isinstance(time_window, str) else "today"
        activity = activity if isinstance(activity, str) else "general"
    # Non-weather intents do not need qualifiers. Nova may return null for
    # those fields despite the schema asking for strings; normalize them to
    # the same bounded defaults used for weather instead of discarding a valid
    # information_lookup classification.
    if intent == "information_lookup" and time_window is None:
        time_window = "today"
    if intent == "information_lookup" and activity is None:
        activity = "general"
    if not isinstance(time_window, str) or not isinstance(activity, str):
        LOGGER.info("weather_extraction_invalid_text_field")
        return None
    if re.search(r"\b(now|right now|currently)\b", user_text, re.IGNORECASE):
        time_window = "now"
    if _parse_coordinates(user_text) is not None:
        location_source = "current"
    normalized_location = _short_ascii(location_text) if location_text is not None else ""
    normalized_current = _short_ascii(current_location_text)
    if intent != "information_lookup" and normalized_location and coordinates is None:
        if location_source == "none":
            LOGGER.info("weather_extraction_location_without_source")
            return None
        if location_source == "current" and (not normalized_current or normalized_location != normalized_current):
            LOGGER.info("weather_extraction_ungrounded_current_location")
            return None
        if location_source == "history" and not _history_location_is_grounded(normalized_location, history):
            LOGGER.info("weather_extraction_ungrounded_history_location")
            return None
    if intent != "information_lookup" and normalized_current and (location_source != "current" or normalized_location != normalized_current):
        LOGGER.info("weather_extraction_current_location_conflict")
        return None
    LOGGER.info("interpretation_location_source source=%s", location_source)
    return {"intent": intent, "activity": _short_ascii(activity) or "general", "time_window": _short_ascii(time_window) or "today", "location_text": normalized_location, "current_location_text": normalized_current, "location_source": location_source, "coordinates": coordinates}


def _current_status_redirect(user_text: str) -> str | None:
    """Keep non-weather current operational questions outside the static guide."""
    lowered = user_text.casefold()
    current_status = re.search(
        r"\b(open|closed|closure|closing|reservation|reservations|book(?:ing)?)\b"
        r"|\b(?:available|availability)\b[^?!.]{0,35}\b(?:campsites?|sites?)\b"
        r"|\b(?:campsites?|sites?)\b[^?!.]{0,35}\b(?:available|availability|open|closed)\b",
        lowered,
    )
    if current_status:
        return "For current openings, closures, reservations, or availability, please check Ontario Parks directly."
    if re.search(r"\b(weather|forecast|temperature|rain|wind)\b", lowered):
        return None
    if re.search(r"\b(fire|fire ban|burn ban|campfire)\b", lowered):
        return None
    if re.search(r"\b(open|available|availability|campsites?)\b", lowered) and not _stable_guide_availability_question(lowered):
        return "For current openings, closures, reservations, or availability, please check Ontario Parks directly."
    if re.search(r"\b(?:today|tomorrow|tonight|this weekend|weekend|this week)\b", lowered) and re.search(r"\b(?:camp|camping|stay|visit|access)\b", lowered):
        return "For current openings, closures, reservations, or availability, please check Ontario Parks directly."
    return None


def _contains_weather_term(user_text: str) -> bool:
    return bool(re.search(r"\b(weather|forecast|temperature|rain|wind|snow|sunny|cold|warm)\b", user_text, re.IGNORECASE))


def _contains_fire_term(user_text: str) -> bool:
    return bool(re.search(r"\b(?:fire|fire ban|burn ban|campfire)\b", user_text, re.IGNORECASE))


def _stable_guide_availability_question(lowered: str) -> bool:
    """Permit stable facilities wording while retaining current site-status redirects."""
    stable_terms = r"\b(facilit(?:y|ies)|canoe rentals?|rentals?|equipment|amenities|activities)\b"
    current_terms = r"\b(today|tomorrow|tonight|weekend|now|currently|this week|site|sites|campsite|campsites)\b"
    return bool(re.search(stable_terms, lowered)) and not bool(re.search(current_terms, lowered))


def _information_lookup_reply(user_text: str) -> str:
    try:
        results = retrieval.configured_retriever().retrieve(user_text)
    except retrieval.RetrievalFailure as error:
        LOGGER.info("rag_retrieval_failed category=%s", error.category)
        return "I couldn't retrieve guide evidence right now. Please check Ontario Parks directly."
    if not results or _conflicting_retrieval(results) or not _has_usable_citation(results):
        LOGGER.info("rag_retrieval_unusable")
        return "The Ontario Parks guide does not establish that answer. Please check Ontario Parks directly."
    evidence = [{"excerpt": item.excerpt, "park_name": item.citation.park_name, "section": item.citation.section, "source_url": item.citation.source_url, "source_label": item.citation.source_label} for item in results]
    try:
        answer = _bedrock_converse(
            system_prompt=RAG_SYSTEM_PROMPT,
            user_text=json.dumps({"question": user_text[:160], "excerpts": evidence}, separators=(",", ":")),
            max_tokens=96,
            temperature=0.0,
            operation_budget="rag",
        )
    except Exception as error:  # noqa: BLE001
        LOGGER.info("rag_response_failed error_type=%s", type(error).__name__)
        return "I couldn't summarize the guide evidence right now. Please check Ontario Parks directly."
    if not _safe_rag_answer(answer, results):
        LOGGER.info("rag_response_rejected")
        return "The Ontario Parks guide does not establish that answer. Please check Ontario Parks directly."
    citation = _citation_suffix(results[0].citation)
    budget = MAX_SMS_CHARS - len(citation) - 1
    return _bound_sms(f"{_bound_sms(answer, '')[:max(0, budget)].rstrip()} {citation}", "The Ontario Parks guide does not establish that answer.")


def _conflicting_retrieval(results: Sequence[retrieval.RetrievalResult]) -> bool:
    """Reject only structured contradictions about the same park, section, and claim."""
    claims: dict[tuple[str, str, str], set[str]] = {}
    for result in results:
        park = result.citation.park_name.casefold()
        section = result.citation.section.casefold()
        if not park or not section:
            continue
        for claim_key, claim_value in result.claims:
            claims.setdefault((park, section, claim_key), set()).add(claim_value)
    return any(len(values) > 1 for values in claims.values())


def _has_usable_citation(results: Sequence[retrieval.RetrievalResult]) -> bool:
    return bool(results) and all(
        result.citation.park_name
        and result.citation.section
        and result.citation.source_url.startswith("https://www.ontarioparks.ca/park/")
        and result.citation.label
        for result in results
    )


def _safe_rag_answer(answer: str, results: Sequence[retrieval.RetrievalResult]) -> bool:
    """Conservatively reject empty, current-status, or ungrounded model prose."""
    normalized = _bound_sms(answer, "")
    if not normalized:
        return False
    if re.search(r"\b(today|tomorrow|tonight|currently|right now|open|closed|closure|available|availability|reservation|reservations|book(?:ing)?|campsites?|fire ban|weather)\b", normalized, re.IGNORECASE):
        return False
    if _answer_conflicts_with_claims(normalized, results):
        return False
    evidence_words = _rag_content_words(" ".join(result.excerpt for result in results))
    answer_words = _rag_content_words(normalized)
    if len(answer_words) < 2:
        return False
    if re.search(r"\b(?:not|no|without|doesn't|does not)\b", " ".join(result.excerpt for result in results), re.IGNORECASE) and not re.search(
        r"\b(?:not|no|without|doesn't|does not)\b", normalized, re.IGNORECASE
    ):
        return False
    overlap = len(answer_words & evidence_words)
    return overlap >= 2 and overlap / len(answer_words) >= 0.45


def _answer_conflicts_with_claims(answer: str, results: Sequence[retrieval.RetrievalResult]) -> bool:
    claim_phrases = {
        "backcountry_camping": r"backcountry camping",
        "winter_camping": r"winter camping",
        "car_camping": r"car camping",
        "walk_in_camping": r"walk[- ]in camping",
        "canoe_rentals": r"canoe rentals?",
        "boat_launch": r"boat launch(?:es)?",
        "canoeing": r"canoeing",
    }
    for result in results:
        for key, value in result.claims:
            phrase = claim_phrases.get(key)
            if phrase is None:
                continue
            match = re.search(phrase, answer, re.IGNORECASE)
            if match is None:
                continue
            prefix = answer[max(0, match.start() - 28):match.start()]
            answer_value = "no" if re.search(r"\b(?:not|no|without|doesn't|does not)\b", prefix, re.IGNORECASE) else "yes"
            if answer_value != value:
                return True
    return False


def _rag_content_words(value: str) -> set[str]:
    ignored = {"about", "and", "are", "based", "does", "for", "from", "guide", "has", "have", "is", "it", "listed", "of", "on", "or", "park", "parks", "that", "the", "this", "to", "what", "with", "yes"}
    return {word.casefold() for word in re.findall(r"[A-Za-z]{3,}", value) if word.casefold() not in ignored}


def _citation_suffix(citation: retrieval.RetrievalCitation) -> str:
    label = f"Source: {citation.label}"
    if citation.source_url.startswith("https://"):
        candidate = f"{label} {citation.source_url}"
        if len(candidate) <= 80:
            return candidate
    return label


def _embedded_json_object(output: str) -> Mapping[str, object] | None:
    if len(output) > 4096:
        return None
    decoder = json.JSONDecoder()
    for index, character in enumerate(output):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            return value
    return None


def _coordinates_from_context(context: Mapping[str, object]) -> tuple[float, float] | None:
    candidate = context.get("coordinates")
    if not isinstance(candidate, Mapping) or set(candidate) != {"latitude", "longitude"}:
        return None
    latitude, longitude = candidate["latitude"], candidate["longitude"]
    if (
        isinstance(latitude, bool)
        or isinstance(longitude, bool)
        or not isinstance(latitude, (int, float))
        or not isinstance(longitude, (int, float))
    ):
        return None
    latitude, longitude = float(latitude), float(longitude)
    return (latitude, longitude) if -90 <= latitude <= 90 and -180 <= longitude <= 180 else None


def _context_created_at(sns_timestamp: object, message_id: object) -> str:
    timestamp = sns_timestamp if isinstance(sns_timestamp, str) and sns_timestamp else str(int(time.time() * 1000))
    identifier = message_id if isinstance(message_id, str) and message_id else "missing-id"
    return f"{timestamp}#{identifier}"


def _normalized_e164(value: object) -> str:
    return context_store.normalized_e164(value)


@lru_cache(maxsize=1)
def _sms_client() -> Any:
    with trace_span("client.init", provider="end_user_messaging"):
        try:
            return boto3.client("pinpoint-sms-voice-v2", config=Config(connect_timeout=5, read_timeout=5, retries={"mode": "standard", "max_attempts": 1}))
        except TypeError:
            return boto3.client("pinpoint-sms-voice-v2")


def _load_context(user_phone: str) -> tuple[list[ContextInteraction], bool]:
    return context_store.load_context(user_phone)


def _context_from_item(item: Mapping[str, Any]) -> ContextInteraction | None:
    return context_store._context_from_item(item)


def _reserve_interaction(user_phone: str, message_id: str, created_at: str, input_body: object) -> bool | None:
    return context_store.reserve_interaction(user_phone, message_id, created_at, input_body)


def _complete_interaction(user_phone: str, message_id: str, created_at: str, input_body: object, output_body: str) -> None:
    context_store.complete_interaction(user_phone, message_id, created_at, input_body, output_body)


def _bedrock_context(current: str, history: Sequence[ContextInteraction]) -> str:
    return bedrock.bedrock_context(current, history)


def _interpretation_bedrock_context(current: str, history: Sequence[ContextInteraction]) -> str:
    return bedrock.interpretation_bedrock_context(current, history)


def _bedrock_converse(*, system_prompt: str, user_text: str, max_tokens: int, temperature: float, history: Sequence[ContextInteraction] = (), prioritize_current: bool = False, operation_budget: str = "standard") -> str:
    return bedrock.bedrock_converse(system_prompt=system_prompt, user_text=user_text, max_tokens=max_tokens, temperature=temperature, history=history, prioritize_current=prioritize_current, operation_budget=operation_budget)


def _bedrock_reply(user_text: object, history: Sequence[ContextInteraction] = ()) -> str:
    if not isinstance(user_text, str):
        user_text = ""
    try:
        return _bound_sms(_bedrock_converse(system_prompt=GENERAL_SYSTEM_PROMPT, user_text=user_text, max_tokens=128, temperature=0.7, history=history), FALLBACK_REPLY)
    except Exception as error:  # noqa: BLE001
        reason = _classify_bedrock_failure(error)
        LOGGER.info("bedrock_reply_failed reason=%s error_type=%s error_code=%s", reason, type(error).__name__, _bedrock_error_code(error))
        return FAILURE_MESSAGES[reason]


def _clarification_reply(user_text: str, history: Sequence[ContextInteraction]) -> str:
    try:
        return _bound_sms(_bedrock_converse(system_prompt=CLARIFICATION_SYSTEM_PROMPT, user_text=user_text, max_tokens=64, temperature=0.0, history=history), WEATHER_EXTRACTION_FALLBACK)
    except Exception as error:  # noqa: BLE001
        LOGGER.info("clarification_reply_failed error_type=%s", type(error).__name__)
        return WEATHER_EXTRACTION_FALLBACK


def _location_request_reply(user_text: str, history: Sequence[ContextInteraction], fallback: str = WEATHER_LOCATION_PROMPT) -> str:
    try:
        return _bound_sms(_bedrock_converse(system_prompt=LOCATION_REQUEST_SYSTEM_PROMPT, user_text=user_text, max_tokens=64, temperature=0.0, history=history), fallback)
    except Exception as error:  # noqa: BLE001
        LOGGER.info("location_request_reply_failed error_type=%s", type(error).__name__)
        return fallback


def _coordinate_correction_reply(user_text: str, history: Sequence[ContextInteraction] = ()) -> str:
    return _bounded_response(COORDINATE_CORRECTION_SYSTEM_PROMPT, user_text, WEATHER_COORDINATE_FALLBACK, history)


def _weather_unavailable_reply(user_text: str, history: Sequence[ContextInteraction] = ()) -> str:
    return _bounded_response(WEATHER_UNAVAILABLE_SYSTEM_PROMPT, user_text, WEATHER_PROVIDER_FALLBACK, history)


def _bounded_response(system_prompt: str, user_text: str, fallback: str, history: Sequence[ContextInteraction] = ()) -> str:
    try:
        return _bound_sms(_bedrock_converse(system_prompt=system_prompt, user_text=user_text, max_tokens=64, temperature=0.0, history=history), fallback)
    except Exception as error:  # noqa: BLE001
        LOGGER.info("bounded_response_failed error_type=%s", type(error).__name__)
        return fallback


def _interpretation_fallback() -> str:
    """Return a deterministic response without attempting a second model call."""
    return WEATHER_EXTRACTION_FALLBACK


def _contains_stale_historical_location(advice: str, history: Sequence[ContextInteraction], verified_location_label: str) -> bool:
    verified = verified_location_label.casefold()
    for interaction in history:
        labels = _historical_location_labels(interaction.input_body) | _historical_location_labels(interaction.output_body)
        for name in labels:
            if name.casefold() != verified and name.casefold() in advice.casefold():
                return True
    return False


def _historical_location_labels(user_text: str) -> set[str]:
    """Extract bounded proper-name candidates solely for stale-output validation."""
    ignored = {"can", "could", "how", "i", "i'm", "it", "please", "the", "today", "tomorrow", "tonight", "weather", "what", "when", "will", "would", "you"}
    labels = set(re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", user_text))
    multiword_tokens = {token.casefold() for label in labels for token in label.split()}
    labels.update(token for token in re.findall(r"\b[A-Z][a-z]+\b", user_text) if token.casefold() not in ignored | multiword_tokens)
    return labels


def _history_location_is_grounded(location_text: str, history: Sequence[ContextInteraction]) -> bool:
    """Accept only the newest available historical proper-name label."""
    for interaction in reversed(history):
        if re.search(rf"\b{re.escape(location_text.casefold())}\b", interaction.input_body.casefold()):
            return True
        labels = _historical_location_labels(interaction.input_body) | _historical_location_labels(interaction.output_body)
        if labels:
            return any(location_text.casefold() == label.casefold() for label in labels)
    return False


def _bound_sms(text: str, fallback: str) -> str:
    return bedrock.bound_sms(text, fallback)


def _short_ascii(value: object) -> str:
    return _bound_sms(value[:48], "") if isinstance(value, str) else ""


def _classify_bedrock_failure(error: Exception) -> str:
    return bedrock.classify_bedrock_failure(error)


def _bedrock_error_code(error: Exception) -> str:
    return bedrock.bedrock_error_code(error)


def _parse_coordinates(user_text: str) -> tuple[float, float] | None:
    match = COORDINATE_PATTERN.search(user_text)
    if match is None:
        return None
    try:
        latitude = _coordinate_value(match.group("latitude"), match.group("latitude_hemisphere"), "NS")
        longitude = _coordinate_value(match.group("longitude"), match.group("longitude_hemisphere"), "EW")
    except (TypeError, ValueError):
        return None
    return (latitude, longitude) if -90 <= latitude <= 90 and -180 <= longitude <= 180 else None


def _coordinate_value(value: str, hemisphere: str | None, valid_hemispheres: str) -> float:
    coordinate = float(value)
    if hemisphere is None:
        return coordinate
    hemisphere = hemisphere.upper()
    if hemisphere not in valid_hemispheres or coordinate < 0:
        raise ValueError("invalid_coordinate_hemisphere")
    return -coordinate if hemisphere in "SW" else coordinate


def _contains_coordinate_attempt(user_text: str) -> bool:
    return COORDINATE_PATTERN.search(user_text) is not None or bool(re.search(r"\b(?:lat(?:itude)?|lon(?:gitude)?|lng)\b|[0-9]{1,3}(?:\.\d+)?\s*[NS]\b", user_text, re.IGNORECASE))


def _sync_location_dependencies() -> None:
    location.urlopen = urlopen
    # Point the resolver at the facade functions so existing monkeypatches and
    # callers that replace a provider continue to work at the Lambda boundary.
    location.search_canadian_geonames = _search_canadian_geonames
    location.search_amazon_places = _search_amazon_places


def _resolve_named_place(place_query: str) -> LocationResolution:
    _sync_location_dependencies()
    return location.resolve_named_place(place_query)


def _search_canadian_geonames(place_query: str) -> list[LocationCandidate]:
    location.urlopen = urlopen
    return _LOCATION_GEONAMES_PROVIDER(place_query)


def _search_amazon_places(place_query: str) -> list[LocationCandidate]:
    location.urlopen = urlopen
    return _LOCATION_AMAZON_PROVIDER(place_query)


def _fetch_weather(latitude: float, longitude: float) -> list[dict[str, object]]:
    weather.urlopen = urlopen
    return weather.fetch_weather(latitude, longitude)


def _lookup_fire_ban(latitude: float, longitude: float) -> fire_ban.FireBanResult:
    return fire_ban.lookup(latitude, longitude)


def _fire_requested(user_text: str) -> bool:
    return bool(re.search(r"\b(?:fire|burn|campfire|ban|burning)\b", user_text, re.IGNORECASE))


def _normalize_hourly_weather(payload: object) -> list[dict[str, object]]:
    return weather.normalize_hourly_weather(payload)


def _select_weather_period(periods: list[dict[str, object]], time_window: str) -> dict[str, object]:
    return weather.select_weather_period(periods, time_window)


def _trip_guidance(weather_data: Mapping[str, object], activity: str) -> list[str]:
    return weather.trip_guidance(weather_data, activity)


def _deterministic_weather_summary(weather_data: Mapping[str, object], guidance: list[str]) -> str:
    return weather.deterministic_weather_summary(weather_data, guidance)


def _number(value: object) -> float:
    return weather.number(value)


def _rank_location_candidates(place_query: str, candidates: list[LocationCandidate]) -> LocationResolution:
    return location.rank_location_candidates(place_query, candidates)
