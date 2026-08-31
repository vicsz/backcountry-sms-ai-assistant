# Stage 6.3 — measured performance improvements

**Status:** Complete; deployed and measured

## Goal

Reduce end-to-end response latency and avoidable dependency work without changing the assistant's
current behavior, reliability boundaries, privacy controls, or two-call Bedrock weather flow.
Every optimization is an experiment: it is implemented independently, deployed explicitly, measured
with real test messages, and retained only when the data demonstrates a material improvement.

## Scope

This stage covers the existing SNS → Lambda → context → interpretation → location → weather →
synthesis → SMS workflow:

1. Reuse lazily initialized module-level AWS clients.
2. Add bounded, per-Lambda-execution in-memory caches for successful location and weather lookups.
3. Remove or correct duplicate ADOT/OpenTelemetry initialization and the non-fatal
   `Attempting to instrument while already instrumented` warning.
4. Add diagnostic tracing and metrics for client construction, cold starts, cache hits/misses, and
   phase timing so the baseline and each experiment can be explained.
5. Produce a durable, source-safe before/after performance record.
6. Test Lambda memory sizing independently because the observed run used 122 MB of a 128 MB
   allocation.

The second Bedrock call for weather advice remains required. No optimization may remove it,
combine it with interpretation, or replace it with a deterministic shortcut in this stage.

## Non-goals

- no distributed cache, new database table, queue, or provisioned concurrency;
- no changes to model selection, prompt behavior, location precedence, weather semantics, or SMS bounds;
- no caching of prompts, SMS bodies, model responses, message history, phone numbers, or precise
  user-linked coordinates in telemetry or durable artifacts;
- no acceptance based only on a plausible code review or a single fast run;
- no automatic deployment or live calls hidden in tests or CI.

## Baseline protocol

Before the first optimization, capture a baseline from the deployed version using the same region,
model, providers, Lambda memory, timeout, and tracing configuration. Use public test inputs and the
existing approved test chat.

At minimum, measure these scenarios separately:

- named location: Toronto;
- GPS-coordinate weather request;
- location-free follow-up using the newest location;
- a repeated Toronto request suitable for cache-hit measurement.

For each scenario, collect at least three cold-start and five warm invocations where practical.
Record the request/reply timestamps separately from Lambda processing time so SMS/SNS delivery
delay is not confused with application latency. A cold start is identified from the Lambda init
signal or an explicit `cold_start=true` invocation metric; it must not be inferred from total SMS
elapsed time alone.

### Baseline deliverable and gate

The initial baseline is a required deliverable **before Experiment A or any performance-changing
implementation begins**. The orchestrator must run the deployed, unoptimized workflow with real
public test messages, inspect the corresponding CloudWatch/X-Ray evidence, and write the results to
the single durable performance document `docs/performance.md`. That document will
contain the initial baseline and all subsequent experiment findings and results.

The initial baseline entry must include:

- deployed commit/version and deployment date;
- exact scenario matrix and sample counts;
- cold and warm p50/p95 tables for end-to-end, Lambda, and each measured phase;
- client-init versus dependency-operation timings;
- Bedrock call counts, token bounds, and usage/cost availability;
- provider call counts, cache state (currently uncached), retries, and response categories;
- Lambda memory/init/billed-duration evidence;
- representative redacted X-Ray and CloudWatch references;
- known gaps, variability, and confidence limits.

The baseline must be committed before the first optimization change is deployed. It is the
comparison reference and must not be overwritten; corrections or additional samples are appended
with a dated note explaining the change. If real baseline data cannot be collected, the stage is
blocked from optimization experiments rather than proceeding with estimates.

## Measurement contract

Each real run must record, without raw payloads:

- deployment/version identifier and experiment name;
- cold or warm classification;
- end-to-end observed SMS latency, Lambda duration, billed duration, and init duration;
- context read, location, weather, interpretation, synthesis, SMS-send, and context-write durations;
- AWS client-construction duration per client, separated from the dependency operation duration;
- cache hit/miss, cache lookup duration, entry count, and eviction count;
- Bedrock call count, configured token ceilings, and provider usage metadata when available;
- provider call count and candidate count where available;
- X-Ray sampled status and trace ID, but not trace payloads;
- outcome and bounded failure category.

If the provider does not return authoritative token usage or rates, retain `estimated_cost: null`.
Do not invent cost values from latency or character counts.

Use p50 and p95 for warm runs as the primary comparison, with cold-start results reported
separately. Also report the number of runs; a result without sample counts is not decision evidence.

## Additional baseline evidence

Before making an optimization decision, capture these additional bounded signals where the platform
or provider exposes them:

- Lambda runtime, memory size, timeout, architecture, deployed version, ADOT layer/wrapper version,
  and whether the invocation was cold or warm;
- Lambda init, runtime overhead, extension overhead, billed duration, maximum memory used, and
  throttles/errors;
- SNS delivery/dwell time, Lambda processing time, SMS provider send time, and observed reply
  delivery time as separate intervals;
- client construction time versus operation time for every AWS client, including whether an
  existing module-level client was reused;
- each dependency's attempt count, retry delay, bounded response category, and timeout budget;
- weather-provider HTTP request, response parsing, normalization, and forecast-selection timing;
- location-provider HTTP/AWS request, candidate parsing, ranking, and selected-result timing;
- Bedrock request count, per-call latency, configured max tokens, response size, and authoritative
  input/output token usage when available;
- DynamoDB query/put operation time, item count returned, pages read, and bounded result count;
- cache lookup time, hit/miss/expired status, entry count, eviction count, and provider calls avoided;
- X-Ray sampling decision, trace availability, and a redacted trace reference for representative
  runs;
- provider HTTP status/category and region, without URLs containing query strings, request bodies,
  headers, or provider payloads.

For each signal, distinguish `not available` from zero. Do not treat a missing trace, missing token
usage, or absent provider timing as a successful zero-latency result. Retain raw timing only in
bounded operational telemetry; the durable performance record stores aggregates and redacted
examples.

The baseline should also note test conditions that can materially affect comparisons: scenario,
time window, cold/warm state, number of prior messages, provider/model configuration, AWS region,
Lambda memory, and whether the result was a cache hit. Weather values themselves are not needed in
the performance record.

## Experiment A — lazy module-level clients

Replace repeated client construction with module-level lazy factories for DynamoDB, Bedrock,
Amazon Location Places, and SMS. Reuse clients and their connection pools across warm Lambda
invocations. Keep the factories injectable/resettable for tests and preserve the existing timeout
and retry configuration.

Add separate spans or metrics for `client_init` and the actual operation. Client initialization
must occur only on the first path that needs that client. A client failure must preserve the
existing bounded fallback behavior and must not poison unrelated clients.

Acceptance requires a measured warm improvement in at least one client-backed operation and no
statistically meaningful regression in cold-start init, error rate, timeout behavior, or reply
correctness. If the experiment does not improve the baseline, revert it.

## Experiment B — location cache

Add a process-local bounded LRU cache for successful, unambiguous location resolutions. Normalize
the lookup key by trimmed, case-folded query text. Do not cache ambiguous, not-found, unavailable,
or failed results.

The cache must have a hard maximum entry count, with an initial proposed default of 128 entries.
It does not need a short normal TTL because location coordinates are relatively stable, but the
maximum size must prevent unbounded growth. A long safety TTL may be added only if provider-data
freshness evidence justifies it. Cache configuration must be environment-controlled for testing.

Cache entries contain only bounded provider-verified location data: normalized label, coordinates,
feature type, region, source, and score. No sender identity or message text may be part of the
cache key or value.

Acceptance requires repeated identical lookups to avoid the provider call, report the hit, preserve
the exact resolved candidate, and demonstrate a real reduction in lookup latency. A miss must be
behaviorally identical to the uncached path.

## Experiment C — weather cache

Add a process-local bounded LRU cache for successful normalized forecasts. Use a key containing the
normalized coordinate pair and all request parameters that affect the forecast. Do not cache
provider failures or malformed responses.

Use a short configurable TTL because weather data changes and stale conditions are unsafe. The
initial proposed default is **5 minutes**, with a hard maximum entry count of 64. A cache hit may
reuse the forecast only within that TTL; an expired entry is a miss and is replaced after a
successful refresh. Cache behavior must never override the requested time window selection.

Acceptance requires a repeated request within the TTL to avoid the weather-provider call, a request
after expiry to refresh it, and measured reduction in provider latency without stale or incorrect
weather responses. The two Bedrock calls must still occur.

## Experiment D — ADOT initialization warning

Determine why the deployed cold start logs `Attempting to instrument while already instrumented`.
Inspect the synthesized Lambda layer, execution wrapper, runtime imports, and initialization logs.
Select one canonical ADOT instrumentation path and remove duplicate initialization rather than
silencing the warning.

Acceptance requires:

- the warning is absent across at least three fresh cold starts, or its source is documented with
  evidence that it is harmless and unavoidable;
- active X-Ray tracing and custom spans remain present;
- cold-start init and steady-state latency do not regress beyond the performance guardrails;
- tracing/export failure still cannot block an SMS reply.

## Experiment E — additional diagnostics

Add bounded diagnostic evidence before optimizing further:

- explicit `cold_start` and initialization duration;
- client initialization versus operation duration;
- cache hit/miss and eviction metrics;
- phase-level spans for context read/write, location, weather, Bedrock interpretation/synthesis,
  and SMS send;
- bounded retry count and dependency outcome;
- total workflow duration and, where possible, SNS/SMS delivery timing separately.

Allowed attributes remain low-cardinality values such as operation, provider, cache result, cold/warm
state, outcome, retry count, and bounded error category. Never add prompts, SMS bodies, history,
coordinates, phone numbers, account IDs, secrets, request headers, or provider payloads.

## Experiment F — Lambda memory sizing

Run a controlled comparison between the current 128 MB setting and an initially proposed 256 MB
setting. Keep code, tracing, model, providers, timeout, and scenario matrix unchanged. Record
billed duration, init duration, maximum memory used, end-to-end latency, and Lambda cost using the
actual AWS pricing context available for the environment. More memory also supplies more CPU and
network capacity, so this is a measured cost/performance experiment rather than an assumption.

Acceptance requires a meaningful latency or reliability improvement whose incremental Lambda cost
is explicitly documented. Do not retain a larger memory size if the measured improvement is below
the stage thresholds or creates an unjustified cost increase.

## Experiment sequencing

Run experiments sequentially:

1. deploy diagnostics and collect the baseline;
2. deploy client reuse and repeat the same matrix;
3. deploy location caching and repeat the same matrix;
4. deploy weather caching and repeat the same matrix;
5. investigate/fix ADOT initialization and repeat cold-start checks;
6. test the memory-size alternative and repeat the same matrix;
7. retain only changes that meet the acceptance and guardrail criteria.

Each experiment must have an explicit configuration switch or a clean isolated commit so it can be
disabled or reverted. Do not combine experiments in one comparison unless the result is clearly
labelled as cumulative rather than attributable to one change.

## Performance guardrails and decision rules

An optimization is accepted only when its evidence shows all of the following:

- the target operation improves by at least 15% at p50 or p95, or end-to-end warm latency improves
  by at least 10%;
- no more than 10% regression in cold-start init, error rate, timeout rate, or end-to-end latency
  for non-cache-hit scenarios;
- no behavior, privacy, tracing, reliability, location-correctness, or SMS-length regression;
- sample counts and test conditions are comparable;
- any cost impact is understood, including cache memory, telemetry, and avoided provider calls.

If an experiment misses these thresholds, document the result and revert or leave it disabled. A
non-improvement is a valid finding and must not be presented as completed optimization.

## Durable performance record

Maintain the single document `docs/performance.md` as a committed, append-only
record of the baseline, experiment findings, measurements, and decisions. Start it with the initial
baseline entry before Experiment A. For every baseline and experiment record:

- date, commit/deployment identifier, configuration, and scenario matrix;
- sample counts and cold/warm classification;
- before/after p50 and p95 tables for end-to-end and phase timings;
- cache hit rates and provider/model call counts;
- observed cost metadata or an explicit `not available`/`estimated_cost: null` statement;
- decision: retain, revert, or inconclusive;
- caveats such as provider variance, cold starts, sampling, or delivery delay.

The document must contain no raw SMS, prompts, model responses, phone numbers, account IDs,
credentials, precise user-linked coordinates, or unbounded logs. Redacted trace IDs and bounded
metric excerpts are allowed when needed to reproduce the evidence.

## Testing and live verification

Unit tests must cover client reuse, factory reset/injection, cache normalization, hit/miss/expiry,
LRU eviction, failed-result non-caching, timeout/retry preservation, cold-start metric behavior,
trace attribute privacy, and unchanged two-call Bedrock behavior.

The live gate must use the same public scenario matrix before and after each experiment, send only
the minimum required test messages, inspect X-Ray and CloudWatch evidence, and record the results
in the durable performance document. No live call belongs in ordinary unit tests or CI.

## Completion gate

Stage 6.3 is complete only when the baseline and each retained optimization have comparable real
measurements, failed experiments are documented, the durable results document is updated, Ruff,
the full unit suite, and `cdk synth` pass, and the final deployed behavior preserves the existing
two-call Bedrock path, follow-up context, one-segment SMS bound, privacy controls, and tracing.
