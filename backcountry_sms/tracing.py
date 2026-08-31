"""Safe, low-cardinality OpenTelemetry spans for the Lambda workflow."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
except ImportError:  # Local tests do not install the Lambda layer.
    trace = None
    Status = StatusCode = None


@contextmanager
def trace_span(operation: str, *, provider: str = "") -> Iterator[None]:
    """Create a bounded span; tracing failures never affect application behavior."""
    if trace is None:
        yield
        return
    try:
        tracer = trace.get_tracer("backcountry_sms")
        span_context = tracer.start_as_current_span(operation)
    except Exception:  # noqa: BLE001
        # Exporter or span setup problems must never break the reply path.
        yield
        return
    with span_context as span:
        span.set_attribute("operation", operation)
        if provider:
            span.set_attribute("provider", provider)
        try:
            yield
        except Exception as error:
            span.set_attribute("outcome", "failure")
            span.set_attribute("error.type", type(error).__name__)
            if Status is not None and StatusCode is not None:
                span.set_status(Status(StatusCode.ERROR))
            raise
        else:
            span.set_attribute("outcome", "success")
            if Status is not None and StatusCode is not None:
                span.set_status(Status(StatusCode.OK))
