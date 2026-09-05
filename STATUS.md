# Project status

This is the single project-status ledger. The detailed requirements and acceptance criteria live
in the individual files under `specs/`. Status claims must be checked against the actual code,
tests, deployment evidence, and current worktree.

## Current release boundary

The deployed core is a bounded SMS-first assistant for an allow-listed sender. It resolves
natural-language locations, retrieves weather, uses bounded Amazon Bedrock interpretation and
synthesis, retains a short encrypted context window, returns one concise SMS, and includes
observability, safe fallbacks, and explicit testing boundaries.

There are no uncommitted Stage 9.2/9.3.2 runtime changes. That work is represented in the
repository at the evidence states below. Stage 10 and Stage 9.2.1 remain documentation-only;
Stage 11 has a local Rust candidate with concrete adapters and isolated opt-in CDK wiring, but it
has not been deployed or live-verified.

Current tracked behavior work: `BUG-0001`, `BUG-0002`, and `ENH-0001` are closed and verified on the
dedicated demo capture stack; this is the project's only deployed environment.

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

## Done locally — not live-verified

| Spec / capability | Evidence status |
| --- | --- |
| Stage 7.1 — model evaluations | Offline and opt-in Bedrock-live evaluation suites implemented; passing evidence recorded |
| Stage 7.2 — location-provider evaluations | Offline and opt-in provider-live evaluation suites implemented; passing evidence recorded |
| Stage 7.3 — evaluation reporting and gates | Local reports, redaction checks, usage/latency evidence, and deterministic gates implemented |
| Stage 9.1 — static typing | Implemented locally; `mypy` build/CI gate and negative check added |
| Stage 9.2 — fire-ban/geospatial lookup | Implemented locally with validated topology, snapshots, and bounded Athena adapter; live S3/Athena deferred |
| Stage 9.3.1 — Ontario Parks guide corpus | MVP corpus generated locally; rerunnable generator and refresh of time-sensitive park information deferred |
| Stage 9.3.2 — Ontario Parks RAG MVP | Implemented and verified on the dedicated capture-mode test stack; one-time ingestion and a redacted retrieval smoke test passed without SMS/SNS; live baseline still returns generic corpus metadata |

## Not done — proposed or deferred

| Spec / capability | Current status |
| --- | --- |
| Stage 8 — broader production reliability | Proposed; burst SMS quota and delivery work remains |
| Stage 9.2.1 — automated fire-ban/geospatial ingestion | Deferred; the Stage 9.2 lookup is implemented locally, but live ingestion, refresh, and promotion are not implemented |
| Stage 9.3 — broader camping RAG knowledge base | Proposed; the Stage 9.3.3 live baseline needs section metadata and negative-query handling before promotion |
| Stage 9.4 — runtime configuration via Parameter Store | Proposed; design only |
| Stage 10 — AI invocation boundary | Proposed; specification only |
| Stage 10.1 — baseline application guardrails | Proposed; specification only |
| Stage 11 — Rust application runtime migration | Partially implemented locally: concrete Rust adapters, 18 passing Rust tests, locked package path, and isolated capture-only candidate definition; Python remains the deployed implementation and no candidate parity/cutover/live gates have passed |
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

1. Validate the isolated Rust candidate locally, then deploy it to the Demo capture target for the
   required redacted capture/provider gates.
2. Run the matched Python-versus-Rust measurement and record only the reviewed aggregate.
3. Keep Python active unless every Stage 11 parity, rollback, and observation gate passes.
4. Rewrite the README and create publication-safe AWS architecture and operations diagrams.
5. Run the public GitHub cleanup checklist before creating a sanitized public copy or fresh initial
   commit.
