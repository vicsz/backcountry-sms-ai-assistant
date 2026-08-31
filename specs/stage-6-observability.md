# Stage 6 — observability MVP

**Status:** Complete; deployed and live resources verified

## Goal

Provide a low-cost, CloudWatch-native view of system health, message processing, dependency
failures, latency, and usage without exposing message content or user-linked sensitive data.

## Scope

The MVP includes:

- Explicit CloudWatch log retention.
- Consistent redacted structured logs.
- A small set of operational metrics.
- One CDK-managed CloudWatch dashboard.
- A small set of actionable email alerts through SNS.
- Tests that verify the logging, metric, retention, dashboard, and alarm contracts.

Tracing, anomaly detection, synthetic monitoring, and automated remediation remain deferred.

## Data-retention contract

- Lambda log retention is explicitly configured to 14 days.
- Log retention must not rely on the CloudWatch default of indefinite retention.
- The Lambda log group is managed by CDK and uses a deliberate removal policy.
- DynamoDB message context retains records for seven days through its existing `ttl` attribute.
- CloudWatch metrics use AWS-managed metric retention; no application TTL is required.
- No raw SMS bodies, prompts, model output, phone numbers, secrets, or precise user-linked
  coordinates are retained in logs or metrics.

## Structured logging contract

Each meaningful processing step emits a bounded JSON-compatible outcome event. Events may include:

- `event`: stable event name;
- `status`: `success`, `ignored`, `fallback`, or `failure`;
- `intent`: `weather`, `general`, or `unclear` where known;
- `provider`: `bedrock`, `nrcan`, `amazon_places`, or `open_meteo` where relevant;
- `reason`: stable redacted failure/outcome category;
- `duration_ms` where measured;
- `bedrock_calls` where relevant.

Required event categories include:

- `sms_received`, `sms_ignored`, `sms_replied`, `sms_send_failed`;
- `bedrock_call`, `bedrock_failure`;
- `location_resolved`, `location_failed`;
- `weather_call`, `weather_failure`;
- `context_read`, `context_write`.

Logging must never include arbitrary exception messages, request bodies, provider payloads, prompts,
model responses, phone numbers, account IDs, secrets, or user-linked coordinates.

## Metrics contract

Publish low-cardinality metrics under one project namespace, for example
`BackcountrySmsAssistant`:

- `MessagesReceived`
- `RepliesSent`
- `MessagesIgnored`
- `FallbackReplies`
- `BedrockCalls`
- `BedrockFailures`
- `LocationResolutions`
- `LocationFailures`
- `WeatherCalls`
- `WeatherFailures`
- `ContextReadFailures`
- `ContextWriteFailures`
- `SmsSendFailures`
- `ProcessingDurationMs`
- `BedrockCallsPerMessage`

Allowed dimensions are fixed values such as `Intent`, `Outcome`, and `Provider`. Never use phone
number, message ID, location, prompt text, response text, or arbitrary error text as a dimension.

Metrics may use CloudWatch Embedded Metric Format or another bounded CloudWatch-native mechanism.
The implementation must avoid duplicate counting on retried SNS deliveries where practical.

## Dashboard contract

Create one CDK-managed dashboard with widgets for:

### Traffic

- Messages received
- Replies sent
- Ignored messages
- Reply success/fallback counts

### Reliability

- Lambda errors and throttles
- Bedrock failures by stable category
- Location and weather provider failures
- SMS send failures
- Context read/write failures

### Latency

- Lambda duration
- Processing duration
- Bedrock call duration where available
- Provider call duration where available

### Usage and cost signals

- Bedrock call count
- Average Bedrock calls per message
- SMS message count
- Lambda invocation count
- DynamoDB read/write activity

The dashboard must not display raw log content or sensitive dimensions.

## Alerting contract

Create an SNS notification topic with an explicitly configured email subscription or documented
manual subscription step. Alerts should be actionable and low-noise:

- Lambda errors exceed a small bounded threshold.
- Messages are arriving but successful replies remain absent for a sustained period.
- Bedrock access-denied or throttling failures exceed a threshold.
- SMS send failures exceed a threshold.
- Processing duration approaches the Lambda timeout.
- Existing account-budget alerts remain the cost ceiling.

Do not send one alert per failed message. Alarms must include evaluation windows and thresholds in
CDK rather than relying on console-only settings.

## Tracing decision

Full X-Ray or OpenTelemetry tracing is out of scope for this MVP. Add tracing only when multiple
Lambdas, queues, or provider latency make correlation difficult. A bounded non-sensitive request
correlation value may be used in logs if it cannot identify a user or expose message content.

## Testing and acceptance

### Unit tests

- Every required event uses a stable event name and redacted fields.
- Logs do not contain phone numbers, SMS bodies, prompts, model output, secrets, coordinates, or
  arbitrary provider payloads.
- Metrics use only approved names and dimensions.
- Failure paths increment the appropriate metric once.
- Duplicate SNS deliveries do not double-count reply outcomes where the existing idempotency logic
  applies.
- CDK defines a 14-day log retention policy.
- CDK defines the dashboard widgets and alarm thresholds.
- Existing message behavior and SMS output bounds remain unchanged.

### Opt-in live checks

Run explicitly with the project integration-test command and the configured SSO profile. Verify:

- A general SMS produces the expected log/metric outcomes.
- A weather SMS produces Bedrock, provider, and reply outcomes.
- A forced or simulated failure produces a fallback and the matching failure metric.
- Dashboard data appears without sensitive fields.
- Alarm notifications can be delivered after the email subscription is confirmed.

Live checks must use public test inputs and redacted output.

## Completion gate

Stage 6 is complete only when:

- Ruff, the full unit suite, and `cdk synth` pass;
- the CDK-managed log group has explicit 14-day retention;
- the dashboard and alarms are deployed;
- live smoke checks confirm redacted logs and expected metrics;
- the existing budget and SMS spend controls remain enabled.

## Non-goals

No raw transcript retention, per-user analytics, prompt/response archives, X-Ray rollout, anomaly
detection, synthetic canaries, automated incident remediation, or new application behavior.
