# Stage 6.3.1 — Nova Micro performance comparison

## Status

Complete; measured in the isolated supported-region test stack. Production remains on Nova 2 Lite
because Nova Micro is unavailable in `ca-central-1` and the small matched sample did not establish
a clean quality win.

## Goal

Evaluate the `us.amazon.nova-micro-v1:0` inference profile as a lower-cost alternative to
the current `us.amazon.nova-2-lite-v1:0` model while preserving the existing two-call Bedrock
workflow, prompts, token ceilings, location/weather behavior, bounded response, and safety rules.
If Nova Micro is materially cheaper and behavior remains comparable—even if latency is merely
comparable—retain Nova Micro as the runtime model after the explicit decision gate.

## Region and access constraint

Model access must be checked before deployment. The current production region is
`ca-central-1`; Nova Micro availability is not assumed there. If it is unavailable in that region,
run the matched experiment against a separately identified test stack in a supported Bedrock
region, recording the region change as a comparison limitation. Never change the production
region as part of this experiment.

For the current US geo inference profile, use `us-east-1` for the dedicated test deployment (the
profile also supports `us-east-2` and `us-west-2`). The exact deployment command is:

```text
CDK_DEFAULT_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 npx aws-cdk deploy --context target=test BackcountrySmsEchoTest --parameters BackcountrySmsEchoTest:AllowedPhoneNumber=<test-value> --parameters BackcountrySmsEchoTest:OriginationIdentity=<test-value> --parameters BackcountrySmsEchoTest:BedrockModelId=us.amazon.nova-micro-v1:0
```

Production remains the existing Lite deployment in `ca-central-1`:

```text
CDK_DEFAULT_REGION=ca-central-1 AWS_DEFAULT_REGION=ca-central-1 npx aws-cdk deploy --context target=production BackcountrySmsEcho
```

The test-region command must be used because Nova Micro is not runnable through this profile from
`ca-central-1`; the CDK rule rejects that model/region combination before resource creation.

## Scope

- Add an explicit deploy-time model selection for the two-call handler, defaulting to the current
  Nova 2 Lite model for production safety.
- Permit only the two experiment model IDs through the test deployment contract. The production
  stack must fail closed if the parameter is anything other than the current Lite model; switching
  production requires a deliberate change after the experiment decision.
- Add the required least-privilege Bedrock resources for Nova Micro and the existing Lite model.
- Run matched live handler invocations through Stage 8.1 capture mode; do not use SMS.
- Collect per-call latency, total Lambda duration, cold/warm state, response outcome, model ID,
  configured token ceilings, and available usage/cost evidence.
- Append before/after findings and the final decision to
  `docs/performance.md`.

## Non-goals

- Do not remove the second Bedrock advice call.
- Do not change prompts, caching, client reuse, memory size, tracing, provider configuration, or
  location/weather logic during this comparison.
- Do not infer cost from latency or response characters when authoritative usage/pricing data is
  unavailable.
- Do not deploy Nova Micro to the production stack until the decision gate passes.
- Do not send or receive real SMS.

## Measurement protocol

1. Confirm model access and supported region/profile.
2. Deploy the isolated test stack with the current Lite model and run 10 public, synthetic,
   carrier-independent handler cases covering named location, GPS, follow-up, repeated lookup,
   and extraction/fallback behavior. Use a fresh synthetic sender/table or an isolated context
   partition for each model so one model cannot consume the other's history or idempotency state.
3. Capture the same 10 cases with the same prompts, token ceilings, memory, timeout, tracing, and
   isolated context using Nova Micro. Run at least three repetitions per model (30 cases/model),
   with the order counterbalanced by repetition; stop if the pre-declared experiment cost ceiling
   is reached.
4. Separate the first cold invocation from warm invocations. Report p50/p95 for total Lambda,
   interpretation call, advice call, and total Bedrock time for cold and warm samples where the
   sample supports it. Report all sample counts and treat p95 as directional when fewer than 20
   warm samples exist.
5. Compare response contract, location extraction, provider path, fallback category, errors,
   retries, and both-call completion. A captured response is not a behavior pass by itself.

## Decision gate

Nova Micro may replace Lite when:

- all required model/provider calls complete or fail only within existing bounded fallback rules;
- no new safety, location, weather, context, or response-bound regressions are observed;
- the matched quality matrix is comparable to Lite;
- authoritative cost evidence shows lower cost, or the model documentation/pricing evidence is
  explicitly recorded as an estimate with its limitations; and
- warm p50/p95 is improved or within a pre-declared 10% tolerance. Latency improvement is preferred but is
  not required when the cost and quality gates pass.

The initial experiment budget is capped at USD 1 of Bedrock usage, excluding standing AWS
resources. Stop the run and record an incomplete result if usage or spend cannot be observed
reliably.

If access is unavailable in the production region, retain the existing model there and record the
regional limitation rather than using an unsupported configuration.

## Durable results

Append one dated section to the performance document containing model IDs, regions,
deployment/version identifiers, sample matrix, p50/p95 tables, per-call timing, errors/fallbacks,
usage/cost evidence, quality observations, limitations, and the retain/revert decision. Do not
include phone numbers, account IDs, message bodies, secrets, or raw provider payloads.
