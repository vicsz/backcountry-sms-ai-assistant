# ENH-0002 — Operational dashboard clarity and recent-error visibility

## Status

Proposed

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

- Only the `BackcountrySmsAssistantTest-ca-central-1` dashboard remains for the project.
- The dashboard clearly identifies `Demo`, `ca-central-1`, and capture mode.
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

To be recorded after implementation. The implementation should preserve the current single-demo
environment boundary and use real CloudWatch metrics/logs rather than invented status values.

## Acceptance and capability tests

To be recorded after implementation. Add deterministic dashboard-template assertions for required
widgets, names, time windows, privacy boundaries, and the absence of a production dashboard. Use an
eval or demo case ID such as `ENH-0002-DASHBOARD-001` for any broader visual or live verification.

## Validation results

To be recorded after implementation. Dashboard changes require the applicable documentation/code
validation gate and an explicit demo-environment inspection.

## Deployment/live-verification status

Required after implementation because the dashboard is deployed infrastructure. Verify the single
remaining demo stack and dashboard in `ca-central-1`; no production deployment or SMS delivery is
part of this enhancement.

## Implementing commit

To be recorded after the change is committed.
