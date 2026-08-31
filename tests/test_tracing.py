from __future__ import annotations

from typing import Self

import pytest

from backcountry_sms.tracing import trace_span


def test_trace_span_is_noop_without_otel_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backcountry_sms.tracing.trace", None)
    with trace_span("weather.lookup", provider="open_meteo"):
        pass


def test_trace_span_does_not_expose_payload_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSpan:
        def __init__(self) -> None:
            self.attributes: dict[str, str] = {}

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def set_attribute(self, key: str, value: str) -> None:
            self.attributes[key] = value

        def set_status(self, _status: object) -> None:
            return None

    span = FakeSpan()

    class FakeTracer:
        def start_as_current_span(self, _operation: str) -> FakeSpan:
            return span

    class FakeTrace:
        @staticmethod
        def get_tracer(_name: str) -> FakeTracer:
            return FakeTracer()

    monkeypatch.setattr("backcountry_sms.tracing.trace", FakeTrace())
    with trace_span("bedrock.converse", provider="bedrock"):
        pass
    assert span.attributes == {"operation": "bedrock.converse", "provider": "bedrock", "outcome": "success"}
