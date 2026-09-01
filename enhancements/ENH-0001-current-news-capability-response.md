# ENH-0001 — Current-news capability response

## Status

Closed

## Capability finding

The synthetic live check `What happened in Ontario today?` was routed to Ontario Parks retrieval
and returned: “The Ontario Parks guide does not establish that answer. Please check Ontario Parks
directly.” This does not explain the assistant’s actual data boundary.

## Desired behavior

The assistant should state concisely that it does not have access to real-time Ontario news or
statistics, and identify supported capabilities such as weather, fire status, and connected
Ontario Parks guide information. It must not fabricate current news or route the question through
unrelated Ontario Parks retrieval.

## Scope and non-goals

- In scope: current-news/current-statistics detection and one-segment capability response.
- Explicitly out of scope: adding a news provider, internet search, or real-time statistics source.

## Acceptance criteria

- Current-news questions bypass Ontario Parks retrieval.
- The response explains unavailable real-time news/statistics and names supported data categories.
- The response fits one SMS segment.
- No current news or statistics are invented.

## Implementation

Added deterministic current-news/current-statistics detection before model and Ontario Parks
retrieval, with a bounded response describing unavailable real-time data and supported capabilities.

## Acceptance and capability tests

- `tests/test_handler.py::test_enh_0001_current_news_explains_data_boundary_without_model_or_retrieval`
  protects routing, capability wording, and the one-segment limit.

## Validation results

Ruff passed; full unit suite passed with 179 tests passing and 19 skipped; CDK synthesis passed.
Demo capture verification passed: the request returned the capability-boundary response and did not
invoke Ontario Parks retrieval.

## Deployment/live-verification status

Required because routing and user-facing behavior run through the deployed Lambda/Bedrock path.
Verified on the deployed `BackcountrySmsEchoTest` stack in `ca-central-1` using capture mode. No SMS
or SNS delivery occurred. No production environment is deployed.

## Implementing commit

To be recorded after the change is committed.
