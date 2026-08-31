# Stage 7 — evaluation program

**Status:** Complete; child specs 7.1–7.3 implemented locally

Stage 7 is split into three sequential, bounded specs:

1. [`stage-7.1-model-evaluations.md`](stage-7.1-model-evaluations.md) — evaluate Bedrock
   interpretation and response calls.
2. [`stage-7.2-location-provider-evaluations.md`](stage-7.2-location-provider-evaluations.md) —
   evaluate real named-place lookup and candidate ranking.
3. [`stage-7.3-evaluation-reporting-and-gates.md`](stage-7.3-evaluation-reporting-and-gates.md) —
   define reports, latency/cost evidence, and stable automated gates.

The evaluation program is a development and release-validation tool, not a user-facing SMS
feature. It must never send SMS, use production message history, or silently turn a live run into
an offline run.

Implement the specs in order. The first two suites must remain independently runnable; the third
consumes their results and adds reporting and enforcement without changing application behavior.
