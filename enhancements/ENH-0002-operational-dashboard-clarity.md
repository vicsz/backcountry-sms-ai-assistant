# ENH-0002 — Operational dashboard clarity and recent-error visibility

## Status

Closed

## Capability finding

The deployed demo dashboard contains useful CloudWatch metrics, but its current layout is visually
busy and does not answer the most important operational questions quickly. The charts have crowded
legends, overlapping latency/usage views, and a large trace-investigation area with little visible
information.

The dashboard should also make recent errors and warnings easy to notice without requiring a user
to open CloudWatch Logs separately.

## Desired behavior

Provide one polished dashboard for the single demo environment that answers at a glance:

- Is the assistant operating normally?
- How many messages, replies, AI calls, and provider calls are occurring?
- Have there been recent errors, warnings, or fallbacks?
- Which dependency or stage needs investigation?
- Is the demo still in capture mode with no carrier delivery?

Include a compact redacted recent-error log view showing useful structured log entries and a short
default time window such as the last hour.

## Scope and non-goals

- In scope: the CDK-managed demo dashboard layout, widget selection, titles, time-window defaults,
  at-a-glance counters, recent redacted error/warning visibility, and demo-boundary labeling.
- In scope: adding stable warning metrics or structured event filters where the current telemetry
  does not make warnings visible.
- Explicitly out of scope: a second environment, a production dashboard, raw transcript browsing,
  arbitrary log search, a new observability service, or changing application behavior solely to
  create dashboard data.

## Acceptance criteria

- Only the `Backcountry-Demo` dashboard remains for the project.
- The dashboard clearly identifies the Demo environment and current live-delivery boundary without
  adding infrastructure detail to the primary view.
- The first view includes concise indicators for messages received, replies sent, AI/model calls,
  provider calls, errors, warnings, fallbacks, and response latency.
- A recent-events/error widget shows the latest redacted structured error and warning entries, or a
  clear no-recent-errors state when none exist.
- The default view uses a short operational window and avoids oversized empty panels.
- Metrics are grouped into understandable sections: health, activity, dependency health, latency,
  safety/delivery boundary, and investigation.
- Error and warning views do not expose SMS bodies, prompts, model responses, phone numbers,
  coordinates, credentials, or raw provider payloads.
- Existing Stage 6 observability metrics, alarm behavior, privacy controls, and dashboard tests
  remain valid.

## Implementation

Implemented in the CDK-managed `BackcountrySmsEchoTest` dashboard. The dashboard now uses a
one-hour default window, a KPI-first layout, explicit Demo/live-delivery labeling, concise
message/call/error counters, a redacted recent-events Logs Insights table, dependency and latency
views, and compact safety/investigation panels. `app.py` now defaults to the single test target and
rejects a production target.

## Acceptance and capability tests

Deterministic coverage is in `tests/test_stack.py`:

- `test_dashboard_is_single_demo_dashboard_for_every_stack`
- `test_dashboard_prioritizes_demo_health_calls_and_recent_redacted_events`

Capability case: `ENH-0002-DASHBOARD-001` — deployed dashboard inspection confirmed the expected
one-hour window, KPI labels, live-delivery boundary, and recent-events widget.

## Validation results

Ruff passed. Full pytest passed: 180 passed, 19 skipped. Python CDK synthesis passed. The npm CDK
wrapper was unavailable offline, so synthesis used the installed Python CDK runtime. `git diff
--check` passed.

## Deployment/live-verification status

Verified 2026-09-01 in `ca-central-1`: `BackcountrySmsEchoTest` is `UPDATE_COMPLETE`, and
`Backcountry-Demo` is the only dashboard returned. No production deployment
was used; live delivery remains limited to the allow-listed demo sender.

## Implementing commit

`e51e1c4` — `ENH-0002 -- simplify demo dashboard and enable live SMS flow`
