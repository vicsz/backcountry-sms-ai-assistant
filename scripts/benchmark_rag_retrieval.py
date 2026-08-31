"""Measure local adapter overhead only; this script never calls AWS."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backcountry_sms.retrieval import LocalRetriever, RetrievalCitation, RetrievalResult


def percentile(samples: list[float], value: float) -> float:
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * value)))
    return ordered[index]


def main() -> None:
    retriever = LocalRetriever([
        RetrievalResult(
            excerpt="Arrowhead lists canoe rentals and a boat launch.",
            citation=RetrievalCitation("Arrowhead", "Facilities", "https://www.ontarioparks.ca/park/arrowhead"),
            score=0.9,
        )
    ])
    samples: list[float] = []
    for _ in range(200):
        started = time.perf_counter()
        retriever.retrieve("What facilities are listed for Arrowhead?")
        samples.append((time.perf_counter() - started) * 1000)
    print(json.dumps({
        "scope": "local_typed_retrieval_adapter_only",
        "samples": len(samples),
        "p50_ms": round(statistics.median(samples), 4),
        "p95_ms": round(percentile(samples, 0.95), 4),
        "telemetry_fields": ["event", "outcome", "duration_ms", "provider", "RetrievalCalls", "RetrievalDurationMs", "RetrievalFailures"],
        "cloud_latency_measured": False,
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
