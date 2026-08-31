"""Low-cardinality CloudWatch Embedded Metric Format telemetry."""

import json
import logging
import time
from collections.abc import Mapping

LOGGER = logging.getLogger("backcountry_sms.telemetry")
LOGGER.setLevel(logging.INFO)
NAMESPACE = "BackcountrySmsAssistant"
METRIC_NAMES = {
    "MessagesReceived", "RepliesSent", "MessagesIgnored", "FallbackReplies",
    "BedrockCalls", "BedrockFailures", "LocationResolutions", "LocationFailures",
    "WeatherCalls", "WeatherFailures", "ContextReadFailures", "ContextWriteFailures",
    "SmsSendFailures", "ProcessingDurationMs", "BedrockCallsPerMessage",
    "LocationCacheHits", "LocationCacheMisses", "WeatherCacheHits", "WeatherCacheMisses",
    "BedrockCallDurationMs", "WeatherCallDurationMs",
    "RetrievalCalls", "RetrievalFailures", "RetrievalDurationMs",
    "ColdStarts",
}
DIMENSION_NAMES = {"Intent", "Outcome", "Provider"}


def emit_event(event: str, status: str, *, provider: str = "", intent: str = "", outcome: str = "", duration_ms: float | None = None, metrics: Mapping[str, float] | None = None) -> None:
    """Emit one bounded JSON event and optional EMF metrics without user data."""
    dimensions = {key: value for key, value in {"Provider": provider, "Intent": intent, "Outcome": outcome}.items() if value and key in DIMENSION_NAMES}
    metric_definitions = [
        {"Name": name, "Unit": "Milliseconds" if name.endswith("Ms") else "Count"}
        for name in (metrics or {})
        if name in METRIC_NAMES
    ]
    record: dict[str, object] = {"event": event[:48], "status": status[:24]}
    if metric_definitions:
        record["_aws"] = {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": NAMESPACE,
                "Dimensions": [list(dimensions)] if dimensions else [[]],
                "Metrics": metric_definitions,
            }],
        }
    record.update(dimensions)
    if duration_ms is not None:
        record["duration_ms"] = round(duration_ms, 2)
    for name, value in (metrics or {}).items():
        if name in METRIC_NAMES:
            record[name] = value
    LOGGER.info(json.dumps(record, separators=(",", ":")))
