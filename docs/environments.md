# Environments and verification targets

This is the authoritative vocabulary for deployment and verification claims in this repository.
Do not describe a target as production unless it is actually deployed and intended to serve real
traffic.

## Current environments

| Environment | Deployment state | Delivery mode | Purpose |
| --- | --- | --- | --- |
| Local | Not deployed | Test doubles/offline fixtures | Unit tests, synthesis, and local iteration |
| Demo | Deployed as `BackcountrySmsEchoTest` | Capture mode | Explicit Bedrock/provider checks with synthetic inputs; no SMS or SNS delivery |
| Production | Not deployed | Not applicable | Future real-SMS deployment target; configuration/specification may exist, but is not live |

## Verification vocabulary

- **Local validation** means lint, unit tests, synthesis, and other offline checks.
- **Demo live verification** means an explicit invocation against the deployed demo stack. It may
  call Bedrock or public providers, but must use synthetic inputs and capture mode.
- **Production live verification** means an explicit check against a deployed production target.
  It requires separate authorization when it could send real SMS or affect production data.
- **Deployed** describes infrastructure that actually exists. A CDK target, stack definition, or
  spec is not evidence of deployment.

Bug records and status documents must name the environment and delivery mode whenever they claim
live verification. If production is not deployed, demo verification is the applicable deployed
gate for this project.
