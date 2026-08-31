"""Bounded, process-local metrics used by the offline evaluation report."""

from __future__ import annotations

from typing import Any

_operations: list[dict[str, Any]] = []


def begin_scenario() -> None:
    _operations.clear()


def record_operation(
    name: str,
    *,
    duration_ms: float,
    input_chars: int = 0,
    output_chars: int = 0,
    max_tokens: int | None = None,
    provider: str | None = None,
    candidate_count: int | None = None,
    network: bool = False,
) -> None:
    operation: dict[str, Any] = {
        "name": name,
        "duration_ms": round(duration_ms, 2),
        "input_chars": max(0, input_chars),
        "output_chars": max(0, output_chars),
        "network": network,
    }
    if max_tokens is not None:
        operation["max_tokens"] = max_tokens
    if provider is not None:
        operation["provider"] = provider
    if candidate_count is not None:
        operation["candidate_count"] = candidate_count
    _operations.append(operation)


def snapshot() -> list[dict[str, Any]]:
    return [operation.copy() for operation in _operations]
