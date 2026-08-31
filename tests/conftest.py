"""Test configuration that keeps jsii's cache inside the ignored project directory."""

import json
import os
import socket
import time
from pathlib import Path

import pytest

from backcountry_sms import bedrock, context_store, handler, location, weather
from backcountry_sms.models import DEFAULT_MODEL_ID
from tests.evals import reporting

os.environ.setdefault(
    "JSII_RUNTIME_PACKAGE_CACHE", str(Path(__file__).parents[1] / ".jsii-cache")
)


def pytest_addoption(parser: object) -> None:
    # Keep evaluation mode explicit while retaining offline as the safe default.
    parser.addoption(
        "--eval-mode",
        action="store",
        default="offline",
        choices=("offline", "bedrock-live", "provider-live"),
        help="evaluation mode; live modes are explicit and bounded",
    )
    parser.addoption(
        "--eval-report-dir",
        action="store",
        default=None,
        help="write a redacted evaluation report under this directory",
    )
    parser.addoption(
        "--aws-region",
        action="store",
        default=None,
        help="AWS region required for live model/provider evaluations",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """Make live evaluation AWS configuration explicit and fail fast."""
    mode = session.config.getoption("--eval-mode")
    if mode not in {"bedrock-live", "provider-live"}:
        return
    region = session.config.getoption("--aws-region")
    if not isinstance(region, str) or not region.strip():
        pytest.exit(
            f"{mode} requires --aws-region, for example --aws-region ca-central-1; "
            "offline evaluations do not require AWS configuration."
        )
    os.environ["AWS_REGION"] = region.strip()
    os.environ["AWS_DEFAULT_REGION"] = region.strip()


def pytest_configure(config: object) -> None:
    config.addinivalue_line("markers", "eval_model: model interpretation and response evaluations")
    config.addinivalue_line("markers", "eval_location: named-place provider evaluations")
    config._eval_results = []


@pytest.fixture(autouse=True)
def clear_cached_aws_clients() -> None:
    """Keep injected test clients isolated while production caches stay process-local."""
    factories = (bedrock._bedrock_client, bedrock._rag_bedrock_client, context_store._dynamodb_client, location._amazon_places_client, handler._sms_client)
    for factory in factories:
        factory.cache_clear()
    location.clear_location_cache()
    weather.clear_weather_cache()
    yield
    for factory in factories:
        factory.cache_clear()
    location.clear_location_cache()
    weather.clear_weather_cache()


def pytest_runtest_setup(item: object) -> None:
    if item.get_closest_marker("eval_model") or item.get_closest_marker("eval_location"):
        reporting.begin_scenario()


@pytest.fixture(autouse=True)
def block_network_for_offline_evals(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = request.node.get_closest_marker("eval_model") or request.node.get_closest_marker("eval_location")
    if marker is not None and request.config.getoption("--eval-mode") == "offline":
        def blocked_connect(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("offline evaluation attempted a network connection")

        monkeypatch.setattr(socket.socket, "connect", blocked_connect)


def pytest_runtest_makereport(item: object, call: object) -> object:
    if getattr(call, "when", None) != "call" or not item.get_closest_marker("eval_model") and not item.get_closest_marker("eval_location"):
        return None
    report_dir = item.config.getoption("--eval-report-dir")
    if report_dir is None:
        return None
    outcome = getattr(call, "excinfo", None)
    status = "passed" if outcome is None else "skipped" if getattr(outcome, "typename", "") == "Skipped" else "failed"
    marker = "model" if item.get_closest_marker("eval_model") else "location"
    scenario = getattr(getattr(item, "callspec", None), "id", item.name)
    operations = reporting.snapshot()
    result = {
        "suite": marker,
        "scenario_id": scenario,
        "fixture_version": "v1",
        "status": status,
        "duration_ms": round(float(getattr(call, "duration", 0.0)) * 1000, 2),
        "deterministic": status,
        "judge": None,
        "estimated_cost": None,
        "operations": operations,
        "call_count": len(operations),
        "input_chars": sum(operation["input_chars"] for operation in operations),
        "output_chars": sum(operation["output_chars"] for operation in operations),
        "max_tokens": max((operation.get("max_tokens", 0) for operation in operations), default=0),
        "network_calls": sum(operation["network"] for operation in operations),
    }
    if marker == "model":
        result["model_id"] = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)
    item.config._eval_results.append(result)
    return None


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    report_dir = session.config.getoption("--eval-report-dir")
    if report_dir is None:
        return
    path = Path(report_dir)
    path.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "run_id": path.name,
        "mode": session.config.getoption("--eval-mode"),
        "exit_status": exitstatus,
        "generated_at_epoch": int(time.time()),
        "results": session.config._eval_results,
    }
    if report["mode"] == "offline":
        forbidden_keys = {"input", "output", "user_text", "current_sms", "history", "phone_number", "account_id"}
        checks = {
            "deterministic_results": all(result["status"] != "failed" for result in report["results"]),
            "offline_network_calls": sum(result["network_calls"] for result in report["results"]) == 0,
            "expected_model_call_counts": all(
                result["call_count"] == 1
                for result in report["results"]
                if result["suite"] == "model" and result["status"] != "skipped"
            ),
            "bounded_report_fields": all(
                key not in forbidden_keys
                for result in report["results"]
                for key in result
            ),
        }
        report["gate"] = {
            "status": "passed" if all(checks.values()) else "failed",
            "checks": checks,
        }
        if not all(checks.values()) and exitstatus == pytest.ExitCode.OK:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
            report["exit_status"] = int(session.exitstatus)
    passed = sum(result["status"] == "passed" for result in report["results"])
    failed = sum(result["status"] == "failed" for result in report["results"])
    skipped = sum(result["status"] == "skipped" for result in report["results"])
    report["summary"] = {"passed": passed, "failed": failed, "skipped": skipped, "total": len(report["results"])}
    (path / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal is not None:
        terminal.write_line(f"Evaluation report: {path / 'report.json'} ({passed} passed, {failed} failed, {skipped} skipped)")
