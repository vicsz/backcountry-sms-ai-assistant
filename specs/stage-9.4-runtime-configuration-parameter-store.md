# Stage 9.4 — Externalized outbound-SMS runtime control

Status: Proposed; design-only MVP specification

## Objective

Provide one operator-controlled outbound-SMS kill switch without requiring an application
deployment and without allowing an ordinary CDK deployment to reset the live value.

This is a narrow runtime-configuration MVP. It is not a general feature-flag, prompt-management,
user-management, or secrets-management system.

## Current configuration boundary

The deployed Lambda currently receives `TEST_MODE` and `SMS_DELIVERY_MODE` as deployment-time
environment variables. Those values remain deployment-controlled because they protect production
and carrier-independent capture-mode separation. This stage adds a separate runtime control for
whether live outbound SMS may proceed.

## MVP parameter contract

Use one manually operated AWS Systems Manager Parameter Store parameter per environment:

```text
/backcountry/<environment>/runtime/outbound-sms-enabled
```

The MVP uses a Standard String parameter with exactly one of these values:

```text
true
false
```

`false` is the emergency stop state. `true` permits the existing deployment-selected delivery
mode to proceed; it does not enable live delivery, disable test isolation, or override any existing
production CloudFormation rules.

The parameter must exist before the associated deployed Lambda is used. Missing, unreadable,
malformed, or unexpected values fail closed: no outbound SMS is sent.

## Ownership and deployment contract

The live parameter value is operator-owned, not application-deployment-owned.

CDK may define or reference the stable parameter name, grant the Lambda narrowly scoped read access,
and configure the Lambda with the parameter path. CDK must not embed the mutable live value in the
application stack template or reset it during an ordinary code, test, or unrelated infrastructure
deployment.

For the MVP, parameter creation and initial value are a separately documented bootstrap operation.
The application stack references the existing parameter rather than declaring an
`AWS::SSM::Parameter` resource with a value that CDK could reapply. Parameter deletion or
replacement must not be an implicit consequence of a Lambda deployment.

## Runtime read semantics

- Read the parameter during every Lambda invocation before any live SMS API call.
- Do not use an environment-variable copy as the source of truth.
- Do not add a cache or Lambda extension in this MVP; a changed value must apply on the next
  invocation.
- Parse only the exact lowercase strings `true` and `false`.
- If the read fails or parsing fails, record a redacted configuration failure and fail closed.
- Never log the parameter value as a raw configuration dump or include it in an SMS response.

The response from Parameter Store may provide a version number. If recorded, retain only the
parameter name, version, and effective bounded state; do not log credentials, message bodies,
phone numbers, or raw provider payloads.

## Delivery and safety rules

The runtime parameter is evaluated only after the existing sender authorization, event parsing,
idempotency, and deployment-mode checks.

The parameter must not be able to:

- turn production capture mode on;
- make a test target send carrier traffic;
- bypass the sender allowlist;
- change the Bedrock model or prompt contract;
- change IAM permissions or provider endpoints;
- override SMS length, GSM-7, safety, or output validation;
- authorize a new user or channel.

When the effective value is `false`, the handler must complete the non-delivery path explicitly and
return a bounded internal outcome. It must not call the SMS provider. Existing context and telemetry
behaviour must be specified so that disabling delivery does not accidentally create misleading
“reply sent” records.

## Operator procedure

The MVP requires a short runbook for an authorized operator:

1. Confirm the exact environment and parameter path.
2. Set the parameter to `false` to stop outbound SMS, or `true` to restore the existing permitted
   delivery mode.
3. Record the reason, operator, time, and intended restoration condition in the operational record.
4. Verify the effective state using redacted telemetry or a carrier-independent deployed capture
   invocation where applicable.

Parameter changes remain subject to AWS IAM authorization and AWS audit history. No automatic
re-enable, scheduled reset, or real-SMS verification is part of this MVP.

## IAM and privacy contract

- Lambda receives `ssm:GetParameter` permission for only the exact environment-specific parameter
  ARN.
- The parameter contains no credentials, API keys, phone numbers, message bodies, or account IDs.
- Parameter names, versions, and effective states may be logged only in redacted, low-cardinality
  telemetry.
- Secrets, if required later, belong in Secrets Manager rather than this parameter.

## Tests and validation

Offline tests must cover:

- `true` permitting the existing eligible live path;
- `false` preventing the SMS API call;
- missing, malformed, unexpected, and unreadable values failing closed;
- unchanged test/capture isolation rules;
- no false “SMS sent” success outcome when delivery is disabled;
- exactly one Parameter Store read per invocation;
- bounded and redacted configuration telemetry.

Infrastructure tests must confirm:

- the Lambda has least-privilege read access to the exact parameter path;
- the application stack does not declare a mutable `AWS::SSM::Parameter` value;
- deployment-time safety parameters remain deployment-controlled;
- the parameter path is stable across ordinary CDK updates.

The opt-in live gate should manually change the parameter on a non-production or explicitly
approved target, invoke the deployed handler through the carrier-independent capture path, verify
the redacted outcome, and restore the prior value. No real SMS send is authorized by this spec.

## Non-goals

- Dynamic configuration documents or arbitrary JSON policy.
- AppConfig, automated rollout, staged percentage releases, or scheduled changes.
- Runtime model, prompt, provider, geography, or safety-policy changes.
- Allowlist or multi-user configuration.
- Secrets storage.
- Replacing CloudFormation deployment parameters for test/live isolation.
- Queueing, retry redesign, or broader Stage 8 reliability work.

## Acceptance criteria

This stage is complete only when:

1. The parameter ownership and bootstrap procedure are documented.
2. A manual value change applies on the next invocation without Lambda code deployment.
3. An ordinary CDK deployment preserves the manually selected value.
4. Missing or unsafe configuration cannot result in outbound SMS.
5. Production/test delivery boundaries remain enforced independently of the parameter.
6. Offline tests and infrastructure assertions cover the contract.
7. An approved carrier-independent deployed check verifies disable and restore behaviour.

Implementation, deployment, and live verification require a separate follow-up change after review.
