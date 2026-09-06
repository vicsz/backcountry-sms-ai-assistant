# ENH-0011 — Remove dead Python request-runtime code

**Status:** Implemented; Rust remains the only deployed request runtime.

## Objective

Remove the former Python Lambda request boundary while preserving Python code that still supports
CDK, fire-ban/RAG ingestion, offline retrieval, provider evaluation, or focused support tests.

## Scope decision

Remove:

- `backcountry_sms/handler.py` as the former Python Lambda entrypoint;
- `backcountry_sms/context_store.py`, which only supported the retired Python request path;
- the historical Python request-runtime test suite;
- the Python SMS client and Python DynamoDB request-context wrappers;
- the old client-reuse coverage for retired SMS/DynamoDB clients.

Retain:

- `models.py` for CDK and shared data contracts;
- `bedrock.py`, `location.py`, `weather.py`, `retrieval.py`, `fire_ban.py`, and `fire_ban_ingestion.py`
  for active offline/evaluation/ingestion capabilities;
- `telemetry.py` and `tracing.py` because retained provider/support modules still use them;
- `support.py` as a deliberately non-deployed offline/evaluation helper surface.

## Non-goals

- Do not change the Rust runtime, deployed Lambda, CDK resource topology, IAM, or SMS behavior.
- Do not remove fire-ban normalization, RAG retrieval tooling, evaluation fixtures, or provider
  support.
- Do not add live provider calls, ingestion, deployment, or SMS sends.
- Do not claim that retained Python support helpers are production runtime code.

## Acceptance criteria

1. No Python Lambda entrypoint, SMS client, or Python DynamoDB context-store module remains.
2. The retained Python module list and ownership are documented.
3. CDK tests assert that the synthesized request path contains no Python Lambda runtime and one
   Rust `provided.al2023` request Lambda.
4. Offline model/provider/fire-ban/RAG tests continue to import only retained support modules.
5. The normal Python validation gate passes without the historical Python request-runtime suite.
6. Rust source, infrastructure, deployed configuration, and deferred ingestion boundaries are
   unchanged.

## Verification record

- Non-legacy Python tests: 76 passed, 19 expected skips.
- Ruff and mypy passed for the retained Python surface.
- Final Rust, Python, offline-evaluation, and CDK-synthesis gates remain required before commit.
