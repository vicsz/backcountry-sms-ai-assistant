# Project status

This is the single project-status ledger. The detailed requirements and acceptance criteria live
in the individual files under `specs/`. Status claims must be checked against the actual code,
tests, deployment evidence, and current worktree.

## Current release boundary

The deployed core is a bounded SMS-first assistant for an allow-listed sender. It resolves
natural-language locations, retrieves weather, uses bounded Amazon Bedrock interpretation and
synthesis, retains a short encrypted context window, returns one concise SMS, and includes
observability, safe fallbacks, and explicit testing boundaries.

Stage 11 is deployed to the Demo request path with Rust as the only Lambda runtime. Python remains
for CDK/support, rollback, and evaluation code. Fire-ban live ingestion remains deferred; the
current work adds only a local normalization/promotion primitive. RAG park scoping and
time-sensitive routing are implemented locally and are promoted only through the normal runtime
validation gate.

Current tracked behavior work: `BUG-0001`, `BUG-0002`, and `ENH-0001` are closed and verified on the
dedicated demo capture stack; `ENH-0003` covers Rust-default hardening and test/documentation
cleanup. This is the project's only deployed environment.

## Done — deployed and verified

| Spec / capability | Evidence status |
| --- | --- |
| Stage 1 — SMS echo | Deployed and verified end to end |
| Stage 2 — Bedrock SMS replies | Deployed and verified |
| Stage 3 — GPS weather and deterministic trip guidance | Deployed and verified |
| Stage 4 — named-place location intelligence | Deployed; live acceptance verified |
| Stage 4.1 — LLM location extraction | Deployed; live acceptance verified |
| Stage 4.2 — current-location precedence | Deployed; live follow-up checks verified |
| Stage 5 — short-lived message context | Deployed and verified; bounded encrypted history with approximately seven-day TTL |
| Stage 6 — observability | Deployed; redacted logs, metrics, alarms, and the redesigned single demo dashboard verified |
| Stage 6.1 — distributed tracing | Deployed; X-Ray/ADOT trace verified |
| Stage 6.2 — reliability | Deployed; bounded retries, idempotency, and failure behavior verified |
| Stage 6.3 — performance improvements | Deployed and measured; retained changes are evidence-backed |
| Stage 6.3.1 — Nova Micro comparison | Measured; production remains on Nova 2 Lite |
| Stage 8.1 — carrier-independent E2E capture | Deployed and verified without carrier traffic |
| Stage 11 — Rust application runtime migration | Rust-only Demo request path deployed and verified; matched capture comparison, X-Ray spans, rollback drill, artifact hash, and 15-minute quiet observation passed; real SMS smoke test not run |

## Done locally — not live-verified

| Spec / capability | Evidence status |
| --- | --- |
| Stage 7.1 — model evaluations | Offline and opt-in Bedrock-live evaluation suites implemented; passing evidence recorded |
| Stage 7.2 — location-provider evaluations | Offline and opt-in provider-live evaluation suites implemented; passing evidence recorded |
| Stage 7.3 — evaluation reporting and gates | Local reports, redaction checks, usage/latency evidence, and deterministic gates implemented |
| Stage 9.1 — static typing | Implemented locally; `mypy` build/CI gate and negative check added |
| Stage 9.2 — fire-ban/geospatial lookup | Implemented locally with validated topology, snapshots, and bounded Athena adapter; live S3/Athena deferred |
| Stage 9.3.1 — Ontario Parks guide corpus | MVP corpus generated locally; rerunnable generator and refresh of time-sensitive park information deferred |
| Stage 9.3.2 — Ontario Parks RAG MVP | Implemented and verified on the dedicated capture-mode test stack; one-time ingestion and a redacted retrieval smoke test passed without SMS/SNS; live baseline still returns generic corpus metadata and is not promoted |
| Stage 9.3.3 — Knowledge-base retrieval tuning | Local park-scoping and time-sensitive routing guardrails deployed with Rust; offline benchmark retained as a diagnostic baseline; metadata, freshness, refresh, and live ranking gates remain deferred |

## Not done — proposed or deferred

| Spec / capability | Current status |
| --- | --- |
| Stage 8 — broader production reliability | Proposed; burst SMS quota and delivery work remains |
| Stage 9.2.1 — automated fire-ban/geospatial ingestion | Deferred; local source normalization and atomic promotion tests exist, but live extraction, refresh, AWS publication, and promotion are not implemented |
| Stage 9.3 — broader camping RAG knowledge base | Proposed; local park-scoping/current-detail gates exist, but the Stage 9.3.3 live baseline still needs section metadata, source-date handling, and a separately authorized promotion |
| Stage 9.4 — runtime configuration via Parameter Store | Proposed; design only |
| Stage 10 — AI invocation boundary | Proposed; specification only |
| Stage 10.1 — baseline application guardrails | Proposed; specification only |
| Multi-channel support and generalized autonomous-agent behavior | Deferred; outside the current release boundary |

## Operational controls already present

- Resource tags, redacted structured telemetry, CloudWatch dashboard/alarms, and active X-Ray traces.
- Least-privilege Bedrock IAM, budget alerts, and SMS sandbox spend controls.
- Bounded prompts, context, retries, model calls, and one-segment GSM-7 output.
- Prompt/output contracts, safe provider/model fallbacks, SNS idempotency, and explicit live-test
  boundaries.
- No credentials, phone numbers, account identifiers, raw message bodies, prompts, model responses,
  or provider payloads in committed fixtures or operational logs.

## Current next actions

1. Keep fire-ban live ingestion deferred; do not present local snapshots or normalized artifacts as live.
2. Keep RAG freshness/source-date handling, corpus refresh, and recurring ingestion deferred until
   the metadata and live retrieval gates are separately authorized.
3. Retire the Python rollback/oracle surface only after another observed Rust-only window and an
   explicit rollback-removal decision; retain Python CDK/support code.
4. Run the public GitHub cleanup checklist before creating a sanitized public copy or fresh initial
   commit.
