# Stage 6.1 — distributed tracing

**Status:** Complete; deployed and live trace verified

## Goal

Make one inbound message visually traceable from SNS through Lambda and its dependency calls so
we can answer which step was slow or failed. Traces are an operational diagnostic aid; they are
not a transcript or message-history feature.

## Scope

Use the AWS Distro for OpenTelemetry (ADOT) Lambda instrumentation and send traces to AWS X-Ray.
Keep the existing SNS → Lambda → provider/Bedrock → SMS topology. Add tracing only to the existing
Lambda; do not introduce another service or queue.

The trace must represent these logical steps when they occur:

1. inbound SNS/Lambda invocation;
2. message-context read;
3. Bedrock interpretation or general-assistant call;
4. location/geocoding call;
5. weather-provider call;
6. Bedrock synthesis call;
7. outbound SMS send;
8. message-context write.

Steps that are not used by a request should not appear as fake successful spans.

## Instrumentation contract

- Enable active tracing on the CDK-managed Lambda.
- Prefer the AWS-managed ADOT Python Lambda layer and OpenTelemetry instrumentation over adding
  the legacy X-Ray SDK as a new dependency.
- Capture AWS SDK operations for Bedrock, DynamoDB, SNS, and other AWS calls where supported.
- Instrument outbound HTTP calls to geocoding and weather providers.
- Add bounded custom spans around the logical application steps listed above.
- Record duration, success/failure status, stable operation name, and a low-cardinality outcome
  category.
- Preserve the existing redacted logging and metric contracts; tracing must not become a second
  transcript store.

## Privacy contract

Never put these values in span attributes, annotations, metadata, exception text, or trace names:

- phone numbers or account IDs;
- SMS bodies, prompts, model responses, or message history;
- secrets, credentials, authorization headers, or provider payloads;
- precise user-linked coordinates or free-form locations.

Allowed attributes are fixed low-cardinality values such as `operation`, `provider`, `intent`,
`outcome`, and bounded error category. Provider hostnames may be recorded when needed to identify
the integration, but query strings and request bodies must be excluded.

## Visual operator experience

The canonical visual view is the AWS X-Ray / CloudWatch ServiceLens trace experience:

- the trace map shows SNS, Lambda, and downstream service/provider nodes;
- an individual trace shows a timeline/waterfall with each custom span and downstream call;
- selecting a span shows duration, status, and stable non-sensitive attributes;
- failed or slow spans can be filtered by service, operation, provider, and outcome.

Create or extend the existing CloudWatch dashboard with:

- Lambda duration, errors, throttles, and invocation count;
- provider/Bedrock failure and latency metrics from the existing observability contract;
- a text/link widget pointing operators to the X-Ray trace map for the deployed service;
- a short operator note explaining how to open a trace and correlate it with the redacted request
  outcome event.

The dashboard is the entry point for health; X-Ray is the detailed visual trace view. Do not copy
raw trace payloads into dashboard widgets.

## Sampling and retention

- Use an explicit, documented sampling rule suitable for a low-volume demo.
- Keep sampling configurable so troubleshooting can temporarily increase coverage without a code
  change.
- Do not promise that every invocation has a trace; the dashboard and metrics remain authoritative
  for aggregate counts.
- Use the AWS-managed X-Ray trace retention behavior unless a later retention requirement is
  approved. This stage does not retain SMS transcripts or prompts in another store.

## Failure behavior

- A tracing/export failure must never prevent processing or an SMS reply.
- Missing tracing context must degrade to ordinary redacted logs and metrics.
- Span creation must be bounded and must not materially change the existing timeout/fallback
  behavior.

## Testing and acceptance

### Unit and infrastructure tests

- CDK enables active tracing and attaches the intended ADOT layer/configuration.
- Required custom operation names are stable and bounded.
- Provider and Bedrock spans record duration/status without payloads.
- Span attributes reject phone numbers, message bodies, prompts, responses, secrets, and precise
  user-linked coordinates.
- Trace/export errors are swallowed safely and do not change the reply path.
- The CloudWatch dashboard contains the required health widgets and X-Ray link/instructions.
- Existing tests, one-segment SMS bounds, redacted logs, and fallback behavior remain unchanged.

### Opt-in live check

Using a public test message and the configured SSO profile, verify that one deployed invocation:

- appears in the X-Ray trace map;
- shows the Lambda timeline and the dependency spans that were actually used;
- exposes duration and status for each visible span;
- contains no SMS body, phone number, prompt, model output, secret, or precise user-linked location;
- leaves the existing CloudWatch dashboard usable when a trace is absent due to sampling.

## Completion gate

Stage 6.1 is complete only when Ruff, the full unit suite, and `cdk synth` pass; tracing is
deployed; the dashboard links to the X-Ray view; and the live check confirms useful spans without
sensitive data or reply-path regressions.

## Non-goals

No full transcript tracing, payload capture, per-user trace search, custom trace database,
OpenTelemetry Collector infrastructure, automated remediation, or SMS connector test mode.
