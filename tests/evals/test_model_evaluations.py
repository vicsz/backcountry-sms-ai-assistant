"""Stage 7.1 model evaluations; live Bedrock calls are explicit via --eval-mode."""

import json
from pathlib import Path
from typing import Any

import pytest

from backcountry_sms import handler
from tests.evals.reporting import record_operation

FIXTURES = json.loads((Path(__file__).parent / "fixtures/model_interpretation.json").read_text())


def _history(rows: list[dict[str, str]]) -> list[handler.ContextInteraction]:
    return [handler.ContextInteraction(row["input"], row["output"], f"fixture-{index}") for index, row in enumerate(rows)]


def _instrument_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    original = handler._bedrock_converse

    def measured(**kwargs: Any) -> str:
        import time

        started = time.perf_counter()
        try:
            result = original(**kwargs)
        finally:
            record_operation(
                "bedrock_converse",
                duration_ms=(time.perf_counter() - started) * 1000,
                input_chars=len(str(kwargs.get("user_text", ""))),
                output_chars=len(result) if "result" in locals() else 0,
                max_tokens=kwargs.get("max_tokens"),
                provider="bedrock",
                network=original is not None and original.__module__ != __name__,
            )
        return result

    monkeypatch.setattr(handler, "_bedrock_converse", measured)


@pytest.mark.eval_model
@pytest.mark.parametrize("fixture", FIXTURES, ids=[fixture["id"] for fixture in FIXTURES])
def test_model_interpretation_contract(fixture: dict[str, Any], request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    mode = request.config.getoption("--eval-mode")
    if mode == "provider-live":
        pytest.skip("provider-live mode does not run model evaluations")
    if mode == "offline":
        monkeypatch.setattr(handler, "_bedrock_converse", lambda **_kwargs: fixture["offline_response"])
    _instrument_bedrock(monkeypatch)

    result = handler._extract_weather_context(fixture["current_sms"], _history(fixture["history"]))

    assert result == fixture["expected"]


@pytest.mark.eval_model
def test_model_live_mode_is_not_silent(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.config.getoption("--eval-mode") != "bedrock-live":
        pytest.skip("requires --eval-mode=bedrock-live")
    monkeypatch.setattr(handler, "_resolve_named_place", lambda _query: pytest.fail("model eval must not call providers"))
    _instrument_bedrock(monkeypatch)
    result = handler._extract_weather_context("I'm in Toronto now, what's the weather?", [])
    assert result is not None
