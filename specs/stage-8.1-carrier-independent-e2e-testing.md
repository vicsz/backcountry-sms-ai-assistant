# Stage 8.1 — Carrier-independent end-to-end testing

## Status

Complete. The dedicated test stack is deployed and verified with direct Lambda invocations;
carrier traffic was not used.

## Goal

Allow the deployed assistant to run realistic end-to-end tests without sending or receiving real
SMS messages. The test must still exercise the deployed Lambda, inbound event parsing, DynamoDB
context, both Bedrock calls, location lookup, weather lookup, response bounding, and observability.

The test mode replaces only the carrier-dependent edges:

```text
synthetic SNS-shaped event -> deployed Lambda -> real providers and context -> captured response
                                      no SNS publish and no SMS API call
```

## Scope

In scope:

- An explicit, deployable test-mode toggle.
- Direct synchronous Lambda invocation with an SNS-shaped fixture.
- Test-only logging of the exact response that would have been sent.
- Continued execution of both Bedrock calls and all configured provider lookups.
- DynamoDB context persistence and follow-up behavior.
- A documented sanity test and repeatable result checks.
- A fail-closed safety boundary preventing capture mode in production.

Out of scope:

- Carrier delivery, mobile-network behavior, or iPhone rendering.
- Real inbound SMS delivery through AWS End User Messaging SMS.
- Increasing SMS throughput or the Sandbox spend limit.
- Replacing the separate, infrequent real-SMS smoke test.

## Configuration contract

Use an explicit deployment setting such as:

```text
TEST_MODE=true|false
SMS_DELIVERY_MODE=capture|live
```

Required behavior:

- `TEST_MODE=true` and `SMS_DELIVERY_MODE=capture` enables capture mode.
- Capture mode must not call `SendTextMessage`.
- Capture mode must not publish an inbound event to SNS.
- The normal production configuration remains `TEST_MODE=false` and
  `SMS_DELIVERY_MODE=live`.
- The production stack name is exactly `BackcountrySmsEcho`; it must reject `TEST_MODE=true` or
  capture mode during CloudFormation validation and Lambda initialization.
- Capture is permitted only on the separately named `BackcountrySmsEchoTest` stack, selected with
  `cdk deploy -c target=test BackcountrySmsEchoTest`, which creates
  its own Lambda, SNS topic, and DynamoDB table. The stack-name guard is part of the deployment
  contract and cannot be overridden by parameters.
- The incoming SMS fixture must never be able to change either setting.
- Test mode should be deployed to a dedicated test stack or explicitly identified test alias;
  repeatedly mutating the production function is discouraged.

## Test sender and message identity

The handler currently authorizes the sender using `ALLOWED_PHONE_NUMBER`. Therefore the fixture's
`originationNumber` must equal the configured allow-listed sender for the deployed test target,
after the handler's normal E.164 normalization.

It must not use:

- The SMS bot's destination number.
- `ORIGINATION_IDENTITY`, which identifies the outbound AWS SMS sender.
- A real personal phone number in a checked-in fixture.

The test deployment should receive its allow-listed fixture sender through deployment configuration
or a secret-free test parameter. A synthetic sender token may be used for the dedicated test target;
no real phone number may be committed. The fixture should use a stable `messageId` per scenario and
a unique test-run suffix when the scenario is repeated, so idempotency behavior can be tested
deliberately.

## Inbound fixture and invocation

Fixtures must match the SNS envelope consumed by `_extract_message`, including an SNS `Message`
string containing the provider message JSON:

```json
{
  "Records": [
    {
      "Sns": {
        "MessageId": "stage-8-1-toronto-001",
        "Timestamp": "2026-08-31T12:00:00Z",
        "Message": "{\"originationNumber\":\"__TEST_SENDER__\",\"destinationNumber\":\"__TEST_BOT__\",\"messageBody\":\"What's the weather in Toronto?\",\"messageId\":\"stage-8-1-toronto-001\"}"
      }
    }
  ]
}
```

The test runner invokes the deployed `BackcountrySmsEchoTest` Lambda directly with `RequestResponse`.
It does not publish the fixture to either SNS topic and does not use the phone connector. The
synthetic sender is configured as the test stack's allow-listed sender; it is not a personal or
production number.

The synchronous invocation result should identify the run, delivery mode, and whether SMS was
called. The result must not expose secrets or real phone identifiers.

## Captured response

When capture mode is active, the outbound adapter records the exact bounded response in a
test-only structured log event, for example:

```json
{
  "event": "test_response_captured",
  "test_run_id": "stage-8-1-toronto-001",
  "delivery_mode": "capture",
  "response": "<bounded response text>",
  "sms_api_called": false,
  "sns_published": false
}
```

The response may also be written to the existing DynamoDB `output_body` for context and follow-up
verification. If it is written there, the record should include an explicit capture/test marker
or use a dedicated synthetic test partition so test history cannot affect real-user context.

Production logs must continue to exclude message bodies and generated response text. Test-only
response logging is permitted because fixtures use synthetic identities and is the primary way to
inspect what would have been sent during this test mode.

## Test matrix

The initial deployed-provider matrix should include:

- Toronto named-place weather request.
- NYC current-location inference.
- A location-free follow-up using DynamoDB history.
- Burnt Island Lake, Algonquin.
- Portage Store.
- GPS coordinates.
- Current location replacing a prior location.
- Ambiguous and unknown named places.
- Bedrock extraction failure or invalid model output.
- Location-provider failure.
- Weather-provider failure.
- DynamoDB read/write failure where safely injectable.
- Duplicate message ID/idempotency behavior.

Each case should verify the captured response, expected provider path, context behavior, and that
no SNS publish or SMS API call occurred.

## Sanity test procedure

After deploying the separately named `BackcountrySmsEchoTest` stack with the synthetic sender:

1. Confirm the target is the dedicated test Lambda or test alias and that `TEST_MODE=true` and
   `SMS_DELIVERY_MODE=capture` are active.
2. Invoke that Lambda directly with the Toronto fixture using
   `scripts/invoke-stage-8-1-test.sh <function-name> <configured-test-sender>`. The helper
   substitutes the configured sender at runtime; no phone number is stored in the repository.
3. Do not send a message through the phone connector and do not publish to the production inbound
   SNS topic.
4. Wait up to 10 seconds for the invocation and log ingestion to complete.
5. Check the test Lambda log group for `event=test_response_captured` and confirm the exact response
   is present.
6. Confirm the capture event says `sms_api_called=false` and `sns_published=false`.
7. Confirm the DynamoDB test record, when persistence is enabled, contains the input and captured
   output under the synthetic test sender.
8. Record the Bedrock/provider result and latency in the test report.

The sanity test is successful only when the response is captured and both carrier-edge calls are
absent. A Lambda success response without the capture event is a failure of the test mode.

## Acceptance criteria

- A deployed test invocation exercises both Bedrock calls and the real configured lookup/context
  path.
- No test-mode invocation calls Amazon End User Messaging SMS.
- No test-mode invocation publishes to the production inbound SNS topic.
- The exact bounded response is visible in the test-only log within 10 seconds.
- Test records cannot contaminate real-user context.
- Production configuration cannot enable test capture.
- The sanity procedure is documented and repeatable.
- Real SMS smoke tests remain explicitly separate and are not hidden in automated tests.

## Evidence to retain

For each run, retain a redacted report containing:

- Scenario and test-run ID.
- Deployed function/version identifier.
- Pass/fail result.
- Captured response.
- Provider/model path.
- DynamoDB context result.
- Total and per-provider latency.
- Confirmation that SNS and SMS were skipped.
- Any failure classification.
