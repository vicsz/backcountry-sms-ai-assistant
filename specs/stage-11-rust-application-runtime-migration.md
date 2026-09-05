# Stage 11 — Rust application runtime migration

**Status:** Proposed; specification only

## Objective

Replace the Python request-processing runtime with a Rust Lambda implementation after proving
behavioral parity, deployment safety, and a useful measured comparison. This is a runtime and
build migration, not a feature expansion. The existing user-visible behavior, provider boundaries,
privacy controls, and SMS safety rules remain the contract.

The final cutover may replace the current Python runtime on the project's normal deployed target
only after the acceptance criteria and live gates in this specification pass. A failed comparison
or incomplete gate stops the migration; it does not justify a partial deployed cutover.

## Current baseline

The current application runtime is a Python 3.12 Lambda with a 25-second timeout, 128 MB memory,
active X-Ray tracing, the Python ADOT Lambda layer, and the existing SNS -> Lambda -> provider,
Bedrock, DynamoDB, and SMS topology. The CDK definition packages the repository asset and points
the function at `backcountry_sms.handler.lambda_handler`.

The source boundary for the runtime replacement is the complete set of application modules under
`backcountry_sms/`: `handler.py`, `bedrock.py`, `context_store.py`, `location.py`, `weather.py`,
`retrieval.py`, `fire_ban.py`, `models.py`, `telemetry.py`, and `tracing.py`. Evidence must
distinguish deployed behavior from locally implemented or fixture-only behavior; porting the local
fire-ban implementation does not make its live data-ingestion path deployed.

The deployed core currently provides:

- allow-listed inbound SMS handling and explicit capture/live delivery modes;
- bounded Bedrock interpretation and synthesis/general-reply calls;
- provider-backed named-place resolution and exact GPS handling;
- weather retrieval, deterministic outdoor guidance, and bounded fallbacks;
- short-lived encrypted DynamoDB context and duplicate-message protection;
- Ontario Parks retrieval/citation behavior;
- a local fire-ban/geospatial implementation whose live data-ingestion path remains separately
  gated;
- redacted CloudWatch metrics, logs, alarms, and X-Ray application spans;
- one-segment GSM-7-compatible SMS output.

The existing performance record is directional rather than a production benchmark. It records a
Python 3.12, 128 MB baseline of one cold and three warm invocations, with approximately 3.6-3.8
seconds of warm Lambda processing and two Bedrock calls for the weather path. Later client/cache
experiments recorded roughly 2.2-2.4 seconds for small warm samples. The comparison in this stage
must rerun a matched baseline rather than treating those historical samples as a definitive target.
The evidence source is [`docs/performance.md`](../docs/performance.md); every new run must also
record the exact implementation commit and deployed function/version.

## Decision boundary

### In scope

- Replace all deployed request-processing code currently under `backcountry_sms/` with Rust, using
  the complete module boundary listed above for parity and eventual Python-runtime removal.
- Preserve the current Lambda event, environment-variable, provider, persistence, telemetry,
  response, and capture-mode contracts.
- Update the CDK Lambda asset, runtime, handler/bootstrap configuration, architecture choice if
  needed, and build packaging so the Rust binary is deployed safely.
- Add Rust unit and integration coverage plus the required black-box deployed comparison.
- Capture and record a redacted Python-versus-Rust performance and call-path comparison.
- Keep a verified Python rollback artifact until Rust cutover is accepted.

### Deliberate boundary

The CDK application remains Python in this stage. AWS CDK officially supports TypeScript,
JavaScript, Python, Java, C#, and Go, but not Rust. Moving infrastructure code to another language
would be a separate migration with its own parity and synthesis review.

Python may also remain temporarily for narrowly scoped deployment helpers or black-box evaluation
scripts if removing it would make the migration less safe. It must not remain in the deployed
request path after cutover.

### Out of scope

- New user-facing capabilities, channels, tools, queues, or autonomous-agent behavior.
- Changes to prompts, approved model selection, provider precedence, SMS limits, fallback wording,
  context retention, or safety policy.
- Expanding or live-verifying the deferred fire-ban ingestion design.
- Rewriting the CDK application in TypeScript, Go, or another language.
- Introducing Python/Rust FFI or a Rust subprocess inside the Python Lambda.
- Treating faster local execution, successful compilation, or a CloudFormation update as proof of
  deployed behavioral parity.

## Target architecture

```text
Python CDK -> Rust binary packaged for Lambda

SNS -> Rust Lambda (provided.al2023) ->
  typed orchestration -> provider adapters / Bedrock / DynamoDB -> SMS
```

Rust Lambda packaging must use the AWS-supported OS-only runtime approach, compile for Linux and
the selected Lambda architecture, and provide the required bootstrap executable. The deployment
must package Rust dependencies with the binary. The existing Python ADOT layer must not be copied
into the Rust function without an explicit compatibility decision and live tracing check.

## Required implementation work

### Runtime and domain behavior

Create a Rust crate for the Lambda runtime and port the application in behavior-preserving layers:

1. Parse the two-layer SNS/provider event and preserve ignored-event behavior.
2. Preserve allow-list normalization, delivery-mode validation, capture behavior, and duplicate
   message handling.
3. Model the interpretation schema with typed structures while retaining runtime validation for
   malformed or adversarial model output.
4. Port location precedence, provider-only coordinates, candidate ranking, ambiguity handling,
   weather normalization, activity guidance, and safe fallbacks.
5. Port the bounded DynamoDB read/reserve/complete flow, including conditional writes, pagination,
   TTL handling, sender isolation, and non-blocking context-read failure behavior.
6. Port Bedrock Converse request envelopes, operation budgets, timeout/retry limits, approved model
   configuration, failure classification, and exact logical call counts.
7. Port retrieval result bounding, citation derivation, claim checks, grounding rejection, and the
   corpus asset needed for citation fallback.
8. Port fire-ban result states, freshness validation, WKT topology/boundary behavior, Athena query
   bounds, and the rule that unresolved status remains `unknown`.
9. Port GSM-7 normalization, extended-character septet counting, output bounding, and all fixed
   fallback messages.

Use typed adapter traits and test doubles for AWS, HTTP, persistence, retrieval, and telemetry
boundaries. Do not translate Python monkeypatching patterns into unsafe global state. Reuse clients
across warm Lambda invocations where the Rust SDK supports it, while preserving test isolation.

### AWS and HTTP adapters

Use the AWS SDK for Rust for Bedrock Runtime, Bedrock Agent Runtime, DynamoDB, Amazon Location
Places, Athena where applicable, and AWS End User Messaging SMS. Use an async runtime and an HTTP
client for the weather and Canadian geocoding providers.

The adapters must explicitly preserve:

- connection and read timeout budgets;
- standard versus single-attempt retry policies;
- service-specific error classification without exposing raw provider details;
- request query encoding and provider response validation;
- IAM action usage and existing environment-variable names;
- no logging of request bodies, prompts, model output, coordinates tied to users, or provider
  payloads.

### Observability

Reimplement the current low-cardinality EMF metrics and application operation names. Preserve
metrics for messages, replies, fallbacks, provider calls/failures, durations, cache hits, cold
starts, and SMS failures.

Recreate custom spans for context, interpretation, location, weather, retrieval, synthesis,
outbound SMS, and context writes only when those operations occur. Active X-Ray platform tracing
may remain enabled, but application-level Rust tracing and any downstream SDK instrumentation must
be proven on the deployed function. A tracing/export failure must remain non-fatal.

## Behavioral parity contract

Rust is accepted only if it preserves the following observable behavior:

- unsupported or unapproved events are ignored without provider or SMS calls;
- capture mode calls neither outbound SMS nor SNS publication;
- live configuration cannot be enabled accidentally from an inbound message;
- current-message location always wins over history;
- provider-returned coordinates are authoritative and invented coordinates are rejected;
- missing, ambiguous, stale, conflicting, or malformed data produces the existing bounded outcome;
- weather-dependent questions do not enter the RAG path incorrectly;
- current status, news, availability, and reservation limitations remain outside static guide data;
- duplicate deliveries stop before a second provider/model/SMS path;
- weather requests retain the expected two logical Bedrock calls;
- guide requests retain retrieval, citation, grounding, and bounded response checks;
- context remains sender-scoped, paginated, bounded, encrypted, and short-lived;
- model/provider failures retain their safe failure categories and fallback behavior;
- output remains one GSM-7 SMS segment and weather advice retains the existing safety limit;
- logs, metrics, traces, reports, and errors remain free of prohibited sensitive data.

## Testing and verification plan

### 1. Freeze and rerun the Python baseline

Before the Rust cutover, rerun a small matched Python baseline using the same region, memory,
timeout, model, delivery mode, fixtures, and scenario order that will be used for Rust. Record the
commit, Lambda version, configuration, sample counts, cold/warm evidence, and any provider/model
failures. Historical measurements may be included for context but must be labeled separately.

### 2. Rust offline tests

Add `cargo test` coverage for deterministic behavior, including:

- SNS/provider event parsing and malformed-event rejection;
- allow-list and capture/live configuration guards;
- JSON schema validation and bounded model failure mapping;
- current/history location precedence and coordinate authority;
- location ranking, ambiguity, provider response validation, and cache behavior;
- weather normalization, period selection, activity guidance, and deterministic fallbacks;
- DynamoDB item parsing, pagination decisions, TTL filtering, and duplicate semantics;
- retrieval bounds, source/citation derivation, claim contradiction, and grounding rejection;
- fire-ban freshness, WKT polygons/holes/multipolygons, boundary handling, and `unknown` results;
- GSM-7 replacement, septet counting, and one-segment output;
- redacted telemetry and tracing attributes.

Rust tests must use deterministic fakes and must not call AWS, public providers, SNS, or SMS.

### 3. Capture-mode contract tests

Run the Rust Lambda through the existing synthetic SNS-shaped event path in capture mode. The
matrix must include:

- GPS weather;
- named-place weather;
- a location-free history follow-up;
- current location replacing historical location;
- RAG guide lookup with citation and grounding checks;
- ambiguous and unknown locations;
- malformed model output and provider failure fallbacks;
- duplicate message delivery;
- invalid delivery configuration;
- context read/write failure behavior.

Every case must verify the returned status, expected logical call path, bounded response, context
isolation, and explicit `sms_api_called=false` and `sns_published=false` evidence. The Rust capture
test must not mutate the normal live target.

### 4. Deployed Rust test verification

Deploy the Rust candidate to a separately identified test function, alias, or test stack before
changing the current Python function. Use the applicable demo target and capture mode first. A
successful Lambda invocation alone is insufficient; inspect redacted logs, metrics, and traces and
confirm the captured response event and absent carrier-edge calls.

Run the smallest useful opt-in live-provider/Bedrock matrix against the deployed Rust candidate.
Use synthetic identities and public test inputs. Do not use personal SMS content or production
data. Fire-ban behavior that has no live data-ingestion gate remains fixture-verified only.

### 5. Rust-versus-Python measurement

Use the same scenario matrix for both implementations, with results stored under ignored `local/`
paths during investigation and a redacted aggregate appended to `docs/performance.md` only after
review. Do not retain prompts, raw provider payloads, phone numbers, account identifiers, or raw
message histories in the permanent comparison.

Capture at least the following for each implementation:

| Dimension | Measurement |
|---|---|
| Artifact | Executable bytes, compressed deployment zip bytes, uncompressed package bytes, build target, commit, and dependency lock state |
| Cold start | Observed `Init Duration`, total duration, billed duration, and maximum memory from Lambda reports |
| Warm execution | Sample count, p50/p95 duration, billed duration, and maximum memory |
| Phase timing | Context read, interpretation, location, weather, retrieval, synthesis, SMS, and context writes where present |
| Calls | Bedrock, retrieval, location, weather, DynamoDB read/write, SMS, retries, fallbacks, and cache hits/misses |
| Output | GSM-7 septets, segment count, response status, safety/fallback outcome, and capture-mode edge flags |
| Observability | Required metrics/spans present, low-cardinality fields, prohibited-data scan, and tracing failures |
| Memory | Lambda `Max Memory Used` as the authoritative operational value; local RSS or binary `size` output only as an explicitly labeled estimate |

Cold samples count as cold only when Lambda reports initialization evidence. Warm samples must be
collected after initialization in the same execution environment where possible. The sample size
may remain intentionally small and directional, but the report must state its limits and must not
claim precise production percentiles.

Do not optimize the Rust implementation during the first parity comparison. Any optimization is a
separate measured change so that language effects are not confused with architecture or behavior
changes.

### 6. Parity oracle and discrepancy rules

The Python implementation is the oracle for deterministic behavior until the Rust implementation
passes cutover. The golden set consists of the existing deterministic handler, location, weather,
retrieval, fire-ban, tracing, client-reuse, and infrastructure tests, plus the deployed capture
matrix in this specification. Each golden case must identify its input fixture, expected logical
provider/model path, expected call counts, expected safety/fallback outcome, and whether context is
read or written.

The following are blocking mismatches:

- any SMS or SNS call in capture mode;
- any changed allow-list, delivery guard, sender isolation, duplicate, context, coordinate, stale
  data, fire-ban uncertainty, grounding, privacy, GSM-7, or fallback behavior;
- any missing, extra, reordered, or incorrectly classified logical provider/model call;
- any model or provider request that violates the existing timeout, retry, model, prompt-envelope,
  or bounded-input contract;
- any missing required metric/span, sensitive telemetry field, or unredacted payload;
- any CDK resource, IAM, environment, retention, test/live-isolation, or deployment-package change
  not explicitly approved by this specification.

Exact generated prose is not a required equality check because model responses can vary. Wording
differences are permitted only when deterministic assertions still pass for intent, location source,
provider-selected coordinates, call counts, citations, safety constraints, fallback category,
segment/septet limits, and context effects. Timing and memory differences are measured separately
and are not parity failures unless they breach the existing Lambda timeout or cause a safety or
delivery failure.

### 7. Normal-target cutover and rollback

After parity, capture, measurement, review, and all applicable live checks pass:

1. Confirm the exact target, account, region, stack, delivery mode, and current deployed version.
2. Preserve the known-good Python artifact and rollback instructions.
3. Synthesize and inspect the CDK template, confirming resource identities, IAM actions, parameters,
   environment variables, timeout, and safety guards remain correct.
4. Deploy the Rust Lambda to the project's normal target. Under the current environment vocabulary,
   the deployed target is the Demo `BackcountrySmsEchoTest`; this repository has no production
   environment unless that definition is separately changed and verified.
5. Use a published Lambda version/alias or an equivalent controlled traffic mechanism when
   available. If the current target cannot provide that mechanism, retain the exact prior Python
   deployment artifact and use an explicit code rollback procedure; do not rely on rebuilding an
   unrecorded historical state.
6. Perform the required deployed capture/provider checks and inspect redacted observability data.
7. Observe the target for at least three successful synthetic scenarios and 15 minutes, with no
   Lambda errors, SMS failures, unexpected calls, or privacy findings. A real SMS smoke test is
   separate and requires explicit authorization immediately before the send.
8. Declare cutover successful only when the observation criteria pass and the redacted comparison
   report is complete. If any criterion fails, roll back to the preserved Python artifact.
9. Verify rollback with one synthetic invocation: the Python runtime must return the expected
   bounded response, preserve the expected logical call path, and produce no Rust-specific runtime
   evidence. Record the rollback result and failure category.

Only after successful cutover and rollback verification may the Python deployed runtime source
be removed from the deployment package and repository. The Python CDK and any explicitly retained
black-box evaluation helpers remain outside that deletion.

## Acceptance criteria

1. The Rust runtime builds reproducibly for the selected Lambda architecture and packages as a
   valid `provided.al2023` Lambda asset.
2. Rust offline tests cover the deterministic contracts listed above and pass without network or
   AWS calls.
3. The capture-mode deployed matrix passes without SNS publication or SMS API calls.
4. The Rust candidate preserves model/provider call counts, context semantics, fallbacks, output
   bounds, and safety/privacy behavior.
5. The Rust candidate's deployed metrics and traces retain the required low-cardinality operational
   evidence without sensitive payloads.
6. A redacted, scenario-matched Python-versus-Rust comparison records artifact size, cold/warm
   timing, memory, phase durations, call counts, retries, fallbacks, cache behavior, and sample
   limitations.
7. CDK synthesis and infrastructure review confirm that the migration did not unintentionally
   change resource topology, IAM scope, retention, or test/live isolation.
8. The normal target is replaced only after the explicit live gates pass, with a known-good Python
   rollback artifact retained until cutover is accepted.
9. After acceptance, the deployed request path contains no Python runtime implementation, and the
   complete `backcountry_sms/` runtime source boundary has been removed or explicitly classified as
   non-production support code.
10. `STATUS.md` and `docs/performance.md` state the actual deployment, evidence, comparison, and
    remaining limitations.

## Final validation gate

The implementation must follow the repository development workflow. After review and the final
focused fix, run the applicable Rust and Python checks once:

- Rust formatting, clippy, tests, and target-architecture release build;
- Ruff, mypy, and pytest for retained Python CDK/evaluation code;
- offline evaluation gates with no network calls;
- CDK synthesis;
- package inspection for `bootstrap`, excluded files, and absence of secrets or private data;
- deployed capture verification;
- explicit live provider/Bedrock verification;
- explicit real-SMS smoke test only when separately authorized.

No deployment, provider call, or SMS send is part of this proposed specification document itself.

## References

- [AWS Lambda: Building functions with Rust](https://docs.aws.amazon.com/lambda/latest/dg/lambda-rust.html)
- [AWS Lambda: Deploy Rust functions with zip archives](https://docs.aws.amazon.com/lambda/latest/dg/rust-package.html)
- [AWS SDK for Rust: Amazon Bedrock Runtime examples](https://docs.aws.amazon.com/sdk-for-rust/latest/dg/rust_bedrock-runtime_code_examples.html)
- [AWS CDK: Supported programming languages](https://docs.aws.amazon.com/cdk/v2/guide/languages.html)
- [AWS Lambda: Working with layers for Rust functions](https://docs.aws.amazon.com/lambda/latest/dg/rust-layers.html)

## Evidence to retain

Retain only redacted evidence:

- implementation commit and Rust toolchain/dependency lock information;
- deployed function/version and target environment;
- scenario-level pass/fail and logical call-count results;
- artifact-size and Lambda timing/memory summaries;
- provider/model failure categories and fallback counts;
- capture-mode proof that SNS and SMS were skipped;
- trace/metric presence and sensitive-data scan results;
- rollback result and any unresolved limitations.

Raw logs, prompts, model responses, provider payloads, credentials, account identifiers, phone
numbers, private URLs, and personal coordinates remain outside the repository and permanent report.
