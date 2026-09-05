# Performance findings and results

This is the single append-only record for the Stage 6.3 baseline and optimization experiments.
Timing values are rounded, bounded operational data. No SMS bodies, prompts, model responses,
phone numbers, account identifiers, credentials, or precise user-linked coordinates are retained.

## Stage 9.3.3 — offline retrieval evaluation capability

Date: 2026-09-05

The repository now contains a deterministic lexical-overlap harness over the checked-in Ontario
Parks guide. It compares fixed 200/20, 300/30, 500/50, and heading-aware chunks at top-k 1, 3,
and 5. The report records corpus hash, candidate ordering, per-case evidence IDs/scores,
independent citation/grounding/refusal rubric results, and current-status routing. The output is
redacted: it retains no raw questions, excerpts, model responses, or provider payloads.

This is an offline retrieval baseline only; its ordering and timings must not be read as Bedrock
embedding, Knowledge Base, generation, or provider-latency measurements. No candidate is approved
for deployment. Live retrieval and any ingestion/deployment decision remain separately authorized.

## Baseline — deployed unoptimized workflow

Date: 2026-08-30
Deployment: commit `458504c` / Stage 6.1 deployed version
Region: `ca-central-1`
Runtime: Python 3.12
Lambda memory: 128 MB
Tracing: active X-Ray with ADOT Python layer
Bedrock flow: two calls per weather request (interpretation and advice)
Caching: none
Sample: 1 cold invocation and 3 warm invocations

### Scenario matrix

| Scenario | State | Lambda duration | Billed duration | Max memory | Result |
|---|---:|---:|---:|---:|---|
| Named location | Cold | 9,657 ms | 10,757 ms | 121 MB | Successful reply |
| Location-free follow-up | Warm | 3,822 ms | 3,823 ms | 121 MB | Successful reply |
| Repeated named location | Warm | 3,786 ms | 3,786 ms | 121 MB | Successful reply |
| GPS-coordinate request | Warm | 3,606 ms | 3,607 ms | 121 MB | Successful reply |

Observed SMS send-to-reply elapsed times were approximately 13 seconds for the cold named-place
run and 6–7 seconds for the warm runs. These include SNS/SMS delivery delay and are not equivalent
to Lambda processing time.

### Warm phase measurements

Warm sample counts are small, so these are directional baseline values rather than stable production
percentiles. p95 uses linear interpolation over the observed samples.

| Phase | Samples | p50 | p95 | Notes |
|---|---:|---:|---:|---|
| Lambda total | 3 | 3,786 ms | 3,819 ms | CloudWatch REPORT duration |
| Handler processing | 3 | 3,643 ms | 3,707 ms | X-Ray application segment |
| Context read | 3 | 285 ms | 285 ms | Actual warm query path |
| Location lookup | 2 | 360 ms | 359 ms | GPS path has no location provider call |
| Weather lookup | 3 | 462 ms | 507 ms | Open-Meteo request plus normalization |
| Bedrock interpretation | 3 | 840 ms | 871 ms | First model call |
| Bedrock synthesis/advice | 3 | 762 ms | 810 ms | Second model call retained by design |
| SMS send | 3 | 354 ms | 362 ms | End User Messaging call |
| Context writes | 6 | 304 ms | 327 ms | Two writes per invocation |

### Cold phase measurements

| Phase | Duration | Notes |
|---|---:|---|
| Lambda init | 1,099 ms | Runtime/layer initialization |
| Context read span | 3,685 ms | Includes client construction plus query path |
| Location lookup | 1,018 ms | NRCAN path |
| Weather lookup | 539 ms | Open-Meteo request plus normalization |
| Bedrock interpretation | 900 ms | X-Ray span |
| Bedrock synthesis/advice | 860 ms | X-Ray span |
| SMS send | 659 ms | X-Ray span |
| Context writes | 267 ms / 400 ms | Reserve and completion writes |
| ADOT extension overhead | 47 ms | X-Ray segment annotation |

### Baseline findings

1. The cold context-read span is the largest apparent setup cost. Warm context reads are only
   approximately 282–285 ms, so the 3.69-second cold span should not be treated as a persistent
   DynamoDB query latency problem. Client construction and SDK initialization must be measured
   separately before and after client reuse.
2. Warm Lambda processing is consistently about 3.6–3.8 seconds in this small sample.
3. The two Bedrock calls account for approximately 1.5–1.7 seconds of warm processing and remain
   required by the Stage 6.3 scope.
4. Weather lookup is approximately 0.44–0.51 seconds warm. Current telemetry measures the total
   request/normalization path, not DNS, connection, TLS, server response, parsing, or retry delay
   separately.
5. Location lookup varies from approximately 0.32–1.02 seconds in the observed traces. The GPS
   scenario correctly avoids the location provider.
6. The Lambda used 121 MB of 128 MB in all four baseline runs, leaving little memory headroom. A
   128 MB versus 256 MB experiment is warranted, but only as a measured cost/performance comparison.
7. The cold start logged the non-fatal warning `Attempting to instrument while already instrumented`.
   ADOT tracing still initialized, the trace was sampled, and all custom spans were present.

### Baseline evidence references

- Cold named-location trace: sampled X-Ray trace captured after the baseline invocation.
- Warm follow-up trace: sampled X-Ray trace captured after the baseline invocation.
- Warm repeated-location trace: sampled X-Ray trace captured after the baseline invocation.
- Warm GPS trace: sampled X-Ray trace captured after the baseline invocation.

Trace IDs are intentionally not retained here; the deployment date, scenario, and CloudWatch
request evidence are sufficient to locate the source data during the active investigation window.

## Experiment log

Each entry uses the same scenario matrix, identifies cold/warm samples, reports before/after
percentiles where the sample is large enough to be useful, states cost/usage-data availability,
and concludes with `retain`, `revert`, or `inconclusive`.

### Experiment A — reuse module-level lazy AWS clients

Date: 2026-08-30
Deployment: post-baseline code deployed from the working tree
Change: cache the Bedrock, DynamoDB, Amazon Places, and End User Messaging boto3 clients per
Lambda execution environment; add `client.init` X-Ray spans. Test fixtures explicitly clear the
caches so unit tests remain isolated.
Configuration held constant: 128 MB, active ADOT tracing, two Bedrock calls, no application
result caches.

#### Real post-change sample

| Scenario | State | Lambda duration | Billed duration | Max memory | Result |
|---|---:|---:|---:|---:|---|
| Named location | Cold | 8,665 ms | 9,803 ms | 123 MB | Successful reply |
| Location-free follow-up | Warm | 2,189 ms | 2,189 ms | 123 MB | Successful reply |
| Repeated named location | Warm | 2,163 ms | 2,163 ms | 123 MB | Successful reply |
| GPS-coordinate request | Warm | 2,409 ms | 2,409 ms | 123 MB | Successful reply |

The cold run's three explicit `client.init` spans totalled approximately 3,006 ms. The largest
was DynamoDB client construction at approximately 2,661 ms. On the warm runs, no `client.init`
spans appeared; warm context reads were approximately 15–226 ms, versus approximately 282–285 ms
in the baseline. This directly supports the client-reuse hypothesis, although the GPS context
read included a slower DynamoDB operation than the other two warm runs.

#### Before/after directional comparison

| Metric | Baseline | Experiment A | Change |
|---|---:|---:|---:|
| Cold Lambda duration | 9,657 ms | 8,665 ms | 10.3% lower |
| Cold billed duration | 10,757 ms | 9,803 ms | 8.9% lower |
| Warm Lambda p50 (n=3) | 3,786 ms | 2,189 ms | 42.2% lower |
| Warm Lambda p95 (n=3, directional) | 3,819 ms | 2,365 ms | 38.1% lower |
| Warm handler p50 (n=3) | 3,643 ms | 2,080 ms | 42.9% lower |
| Warm weather p50 (n=3) | 462 ms | 452 ms | 2.1% lower |

The warm end-to-end reduction is real in this sample, but it is not safe to attribute all of it
to client reuse: the two Bedrock calls were also faster in Experiment A. The strongest isolated
evidence is the disappearance of warm client-construction spans and the reduction in warm context
read time. Weather lookup did not materially change, as expected.

#### Decision: retain

Retain Experiment A for the next experiment. It removes approximately three seconds of measured
cold client setup in the sampled cold start and avoids that setup on warm invocations, with no
functional failures. This is a provisional decision based on a small real sample, not a stable
production percentile or a precise per-request dollar estimate. The ADOT duplicate-instrumentation
warning remained and is not resolved by this change. Max memory increased from 121 MB to 123 MB,
so the later memory-sizing experiment remains required.

Cost data: Lambda billed-duration data is available above. Bedrock/provider and SMS per-request
costs were not emitted by the application and are not estimated here; client reuse does not reduce
the required two Bedrock calls.

### Experiment B — bounded location cache

Date: 2026-08-30
Deployment: Experiment A plus the process-local location cache
Change: cache successful, unambiguous resolutions using trimmed, case-folded query text; retain at
most 128 entries by default; do not cache failures or ambiguous results; emit hit/miss metrics.
Configuration held constant: 128 MB, active ADOT tracing, two Bedrock calls, no weather cache.

#### Real matched sample

Two identical `Weather in Toronto now.` requests were sent through the same live Lambda execution
environment. The first request was a cold cache miss; the second was a warm cache hit.

| Scenario | Cache result | Lambda duration | Billed duration | Location path | Result |
|---|---:|---:|---:|---:|---|
| Named location | Miss, cold | 8,820 ms | 9,775 ms | Provider lookup 589 ms | Successful reply |
| Same named location | Hit, warm | 1,781 ms | 1,782 ms | Cache span 0.09 ms; provider skipped | Successful reply |

The cache-hit trace contains no `location.lookup` provider span, while the miss contains the
NRCAN lookup and `LocationCacheMisses=1`. The hit contains `LocationCacheHits=1`; both requests
still made two Bedrock calls and one weather call. The hit reduced the measured location phase by
approximately 589 ms, but the total Lambda difference also includes cold initialization and normal
provider/model timing variation.

#### Decision: retain

Retain the location cache. It demonstrably avoids the named-location provider call, preserves the
resolved response, and adds no external state or freshness risk for the bounded coordinate data.
The real sample is sufficient to establish provider avoidance and the expected sub-millisecond
cache path, but not to claim a stable end-to-end percentage or production p50/p95.

### Experiment C — bounded five-minute weather cache

Date: 2026-08-30
Deployment: Experiments A and B plus the process-local weather cache
Change: cache successful normalized forecasts by rounded coordinate pair for five minutes, with a
maximum of 64 entries; expired and failed values are not reused; emit hit/miss metrics.
Configuration held constant: 128 MB, active ADOT tracing, two Bedrock calls, location cache on.

#### Real matched sample

Two identical `Weather in Toronto now.` requests were sent within the same execution environment.
The first request missed both caches and fetched location and weather; the second hit both caches.

| Scenario | Cache result | Lambda duration | Billed duration | Weather path | Result |
|---|---:|---:|---:|---:|---|
| Named location | Location miss, weather miss, cold | 8,960 ms | 10,026 ms | Provider call 449 ms | Successful reply |
| Same named location | Location hit, weather hit, warm | 1,643 ms | 1,643 ms | Cache hit; provider skipped | Successful reply |

The hit emitted `LocationCacheHits=1` and `WeatherCacheHits=1`; it emitted no
`weather_call` event. Both Bedrock calls still occurred. The weather cache path therefore avoided
approximately 449 ms of measured weather-provider work in this real sample, with no stale-value
window beyond the configured five-minute TTL.

#### Decision: retain

Retain the weather cache. It demonstrably avoids a repeat provider call while preserving the
required model calls and bounded freshness policy. The end-to-end difference is not attributed
entirely to caching because the comparison includes cold initialization and provider/model
variation; the provider-call avoidance is the reliable result.

### Experiment D — ADOT initialization warning

Date: 2026-08-30
Change: investigation only; no tracing configuration change retained.

The warning `Attempting to instrument while already instrumented` appeared during at least three
fresh cold starts across the baseline, client-reuse, location-cache, and weather-cache deployments.
The synthesized template consistently showed active X-Ray tracing, the AWS-managed ADOT Python
layer, and the `INSTRUMENT_HANDLER` execution wrapper. The application itself does not call a
global instrumentation or patch-all routine; its tracing helper only creates individual spans.

Each affected cold start still exported a sampled X-Ray trace containing the application segment,
custom phase spans, provider subsegments, and the new client/cache spans. Replies succeeded, so
there is no evidence that the warning represents a functional instrumentation failure. The exact
duplicate initialization is inside the managed ADOT Lambda startup path and is not exposed by the
application code or synthesized CloudFormation configuration.

#### Decision: inconclusive / leave unchanged

Do not remove the managed ADOT layer or wrapper without a replacement tracing design. The current
evidence supports documenting the warning as non-fatal and preserving the canonical configured
path. A future ADOT layer-version comparison may be worthwhile, but changing it here would mix a
runtime-layer experiment with the application performance measurements.

### Experiment E — diagnostics and percentile-ready metrics

Date: 2026-08-30
Change: publish `ProcessingDurationMs`, `BedrockCallDurationMs`, `WeatherCallDurationMs`, and
`ColdStarts` as bounded CloudWatch metrics; retain the existing phase spans and add dashboard
widgets using p50 and p95 statistics.

A real deployed request emitted two Bedrock duration metrics (approximately 852 ms and 542 ms),
one weather duration metric (approximately 577 ms), a workflow duration of approximately 7,520 ms,
and a cold-start indicator of 1. The request completed successfully and preserved the two-call
Bedrock path. This supplies the data needed for operational p50/p95 tracking; the current sample
is too small to call those values production percentiles.

#### Decision: retain

Retain the diagnostics. They make the next performance decisions measurable without recording
prompts, SMS bodies, coordinates, phone numbers, or provider payloads.

### Experiment F — Lambda memory sizing

Date: 2026-08-30
Comparison: 128 MB matched against 256 MB with the retained client and cache changes enabled.

| Scenario | 128 MB | 256 MB | Change |
|---|---:|---:|---:|
| Cold Lambda duration | 8,960 ms | 4,429 ms | 50.6% lower |
| Cold billed duration | 10,026 ms | 5,554 ms | 44.6% lower |
| Cold max memory | 121 MB | 171 MB | 50 MB higher |
| Warm Lambda duration | 1,643 ms | 1,265 ms | 23.0% lower |
| Warm billed duration | 1,643 ms | 1,265 ms | 23.0% lower |

Using billed duration multiplied by configured memory as a relative Lambda compute proxy, 256 MB
was approximately 11% more expensive for the cold sample and 54% more expensive for the warm
sample. Bedrock, weather, and SMS charges were not changed by memory size, and the required two
Bedrock calls remained present. The 256 MB run used 171 MB, while the 128 MB run used approximately
121–124 MB, confirming both the performance benefit and the limited headroom at 128 MB.

#### Decision: revert

Revert to 128 MB. The faster 256 MB setting does not reduce the cost target and its incremental
Lambda compute cost is not justified for this workflow at the observed sample size. The memory
headroom concern remains an operational follow-up; it should be revisited with a larger sample or
a more targeted dependency/startup reduction rather than silently retaining the higher setting.

### Observation sample — 10 live requests after Stage 6.3

Date: 2026-08-30
Deployment: final retained Stage 6.3 configuration at 128 MB

Ten public test requests were sent through the live SMS connector using named locations,
location-free follow-ups, GPS requests, and repeated locations. The messages were sent as a rapid
burst, so Lambda created multiple concurrent execution environments rather than one long-lived
warm environment.

#### Observed Lambda metrics

| Population | Samples | p50 | p95 | Notes |
|---|---:|---:|---:|---|
| All Lambda REPORT durations | 10 | 4,053 ms | 8,859 ms | Directional; includes concurrent cold starts |
| Cold Lambda REPORT durations | 4 | 9,637 ms | 10,015 ms | Init durations approximately 888–1,130 ms |
| Warm Lambda REPORT durations | 6 | 2,525 ms | 4,808 ms | One slower concurrent warm invocation |
| Billed duration | 10 | 4,053 ms | 8,859 ms | Total billed duration: 51,630 ms |

Maximum memory used ranged from 114 MB to 121 MB of 128 MB. Four of ten requests reported a
cold-start metric. These p50/p95 values are now visible through the dashboard metrics but remain
directional until a larger, less bursty sample is collected.

#### Dependency and cache observations

- Bedrock: 19 successful model-call records, indicating one request did not reach its second model
  call after interpretation failed; the normal two-call path remained intact for successful flows.
- Weather: 8 provider calls, with 1 weather-cache hit and 8 misses recorded.
- Location: 1 location-cache hit and 6 misses recorded; GPS and the failed interpretation path do
  not perform named-place lookup.
- SMS: 7 successful replies and 3 `ServiceQuotaExceededException` send failures during the rapid
  burst. This constrains the sample’s end-to-end success rate to 70% and should not be interpreted
  as an application logic failure.
- No application exceptions, stale-cache events, or tracing loss were observed in the completed
  Lambda records.

#### Interpretation

The sample confirms the metrics are being emitted and that cache behavior is correctly scoped to
warm execution environments. It is not a clean steady-state cache-rate benchmark because the
burst deliberately caused concurrent environments and hit the SMS quota. The next observation
sample, if needed, should space requests far enough apart to avoid provider quota interference and
should include repeated requests on one warm environment.

## Stage 6.3.1 implementation note — model selection

Date: 2026-08-31

The CDK deployment contract now allows only `us.amazon.nova-2-lite-v1:0` and
`us.amazon.nova-micro-v1:0` (the US geo inference profile is
`us.amazon.nova-micro-v1:0`). Production defaults to and fails closed on Nova 2 Lite; the dedicated
`BackcountrySmsEchoTest` stack defaults to Nova Micro and can select either allowed model through
the `BedrockModelId` parameter. Nova Micro test deployments are guarded to `us-east-1`,
`us-east-2`, or `us-west-2`; production remains `ca-central-1` Lite. The Lambda environment
passes that parameter to both existing Bedrock calls, and conditional IAM policies authorize only
the selected model path.

This was the implementation record before the measured comparison appended below. The production
model remained unchanged during the experiment.

## Stage 6.3.1 measured Nova Micro comparison

Date: 2026-08-31

The access preflight confirmed that Nova Micro is not listed for the production `ca-central-1`
region, while the US geo inference profile is active in `us-east-1`. A separate, carrier-independent
test stack was therefore used in `us-east-1`. Production was not changed.

The same 10 synthetic cases were invoked once per model through the deployed Stage 8.1 capture
mode, using separate sender/context partitions. The cases covered GPS, Toronto, Burnt Island Lake,
Portage Store, a follow-up, NYC, repeated Toronto, and an unknown place. Both runs used the same
128 MB Lambda, prompts, token ceilings, providers, tracing, and two-call workflow. All 20 Lambda
invocations returned `status=captured`, and every captured event reported `sms_api_called=false`
and `sns_published=false`.

### Observed timing

| Measure | Nova 2 Lite (n=10) | Nova Micro (n=10) | Change |
|---|---:|---:|---:|
| Bedrock call p50 | 614 ms (16 calls) | 491 ms (15 calls) | 20.0% lower |
| Bedrock call p95 | 869 ms | 564 ms | 35.1% lower |
| Handler processing p50 | 1,447 ms | 876 ms | 39.5% lower |
| Handler processing p95 | 2,586 ms | 2,203 ms | 14.8% lower |

The timing comparison is directional: each model had only 10 handler samples, the runs were
sequential rather than randomized, and fewer than 20 warm samples were available for a stable p95.
No Bedrock service errors were observed. Lite emitted 16 successful Bedrock calls and Micro 15;
the difference reflects model-response/path behavior in this small scenario set, not a proven
reliability advantage.

### Quality and cost evidence

Both models produced bounded capture responses, but both showed variable natural-language location
handling. The Micro run successfully resolved some named-place/current-location cases that Lite
missed, while also missing other cases; this is not sufficient to declare quality comparable with
confidence. The existing location-extraction weakness remains a separate behavior issue.

Authoritative per-model Bedrock cost was not available from the captured Lambda logs or the
available account-level usage view, so no dollar amount is claimed here. The model-access
documentation identifies Nova Micro as the lower-cost/low-latency option, but that documentation is
not a substitute for measured account billing.

### Decision

Do not switch production yet. Nova Micro is not available in the production `ca-central-1` model
path, and the small, sequential sample does not clear the quality gate despite the encouraging
latency result. The explicit model-selection contract and isolated test path are retained so a
future supported-region or availability change can rerun a larger randomized comparison. The
production model remains `us.amazon.nova-2-lite-v1:0`.

## Stage 9.3.2 local retrieval benchmark

Run this explicit offline benchmark after a code change that affects the local retrieval contract:

```text
.venv/bin/python scripts/benchmark_rag_retrieval.py
```

It reports p50 and p95 milliseconds for the typed local retrieval adapter over 200 in-process
lookups. It makes no AWS, Bedrock, SMS, geocoding, weather, or fire-ban call. Its output is not a
cloud-latency claim.

Production telemetry for a future explicit smoke test should emit only event/outcome/category,
duration milliseconds, provider, and `RetrievalCalls`, `RetrievalDurationMs`, and
`RetrievalFailures` metrics. It must not emit questions, excerpts, source payloads, phone numbers,
or raw Bedrock responses.

### One-time deployment and sync

The CDK stack creates the versioned S3 corpus object, the S3 Vectors bucket/index, and the Bedrock
Knowledge Base/data source. Stack outputs provide generated knowledge-base and data-source IDs,
the corpus URI, and the committed corpus SHA-256. Do not copy those generated IDs into source.

After an authorized deployment, use the SSO profile and output IDs to run one explicit
`bedrock-agent start-ingestion-job` command. Confirm the job completes before any separately
authorized, redacted `retrieve` smoke test. No scheduled ingestion, source polling, or automatic
refresh is configured.

### Stage 9.3.2 live capture evidence — 2026-08-31

The dedicated `BackcountrySmsEchoTest` stack was deployed in `ca-central-1` with capture mode
enabled. The one-time Bedrock Knowledge Base ingestion completed successfully. A direct Lambda
invocation using the representative Portage-area question `What activities does Algonquin
Provincial Park list?` returned a captured, source-attributed answer and confirmed
`sms_api_called=false` and `sns_published=false`.

Observed redacted timings for that invocation were: extraction Bedrock 882 ms, Knowledge Base
retrieval 1,108 ms, answer Bedrock 667 ms, and total Lambda processing 6,340 ms. Retrieval returned
an Algonquin result with score 0.949. The response was bounded to one SMS segment and cited
`Ontario Parks - Algonquin Provincial Park`. These are single-run observations, not p50/p95
claims; the existing metrics remain the source for percentile aggregation.
