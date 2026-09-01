# Environments and verification targets

This is the authoritative vocabulary for deployment and verification claims in this repository.
Do not describe a target as production unless it is actually deployed and intended to serve real
traffic.

## Current environments

| Environment | Deployment state | Delivery mode | Purpose |
| --- | --- | --- | --- |
| Local | Not deployed | Test doubles/offline fixtures | Unit tests, synthesis, and local iteration |
| Demo | Deployed as `BackcountrySmsEchoTest` | Live delivery | Explicit Bedrock/provider checks and allow-listed SMS delivery; no production traffic |
| Production | Not deployed | Not applicable | No production environment exists in this repository |

## Verification vocabulary

- **Local validation** means lint, unit tests, synthesis, and other offline checks.
- **Demo live verification** means an explicit invocation against the deployed demo stack. It may
  call Bedrock or public providers; SMS delivery is limited to the allow-listed demo sender.
- **Production live verification** means an explicit check against a deployed production target.
  It requires separate authorization when it could send real SMS or affect production data.
- **Deployed** describes infrastructure that actually exists. A CDK target, stack definition, or
  spec is not evidence of deployment.

Bug records and status documents must name the environment and delivery mode whenever they claim
live verification. If production is not deployed, demo verification is the applicable deployed
gate for this project.
