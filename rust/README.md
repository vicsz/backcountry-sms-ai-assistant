# Stage 11 Rust runtime slice

This directory contains the compileable local capture slice of the Stage 11 migration. The
`bootstrap` binary uses the AWS Lambda Rust runtime and the injected orchestration currently
implements:

- nested SNS/provider event parsing;
- allow-list normalization and fail-closed delivery configuration;
- strict typed interpretation validation;
- GSM-7 normalization, septet counting, and one-segment bounding;
- deterministic general/weather/information-lookup/fire-status routing;
- retrieval citation and grounding guards;
- fire-ban snapshot freshness and validated WKT polygon/multipolygon membership;
- side-effect adapter traits, bounded timeout/retry configuration, and deterministic fakes.

The local capture harness injects deterministic fakes and records logical calls. It does not call
Bedrock, HTTP providers, DynamoDB, retrieval, Athena, SNS, or SMS. The active Python Lambda remains
the oracle and deployed request path until parity and cutover gates pass.

## Local checks

From this directory:

```text
make fmt
make test
make clippy
```

The Lambda package target is `x86_64-unknown-linux-gnu`, matching the existing CDK default
architecture. `rust-toolchain.toml` pins the compiler and target for a rustup-enabled Linux build;
the local Homebrew toolchain can still run host tests but cannot install that target by itself.

The Python CDK remains unchanged in this slice. Wiring this package into a separately identified
candidate function requires concrete AWS/HTTP adapter implementations and the capture/deployed
parity gates; replacing the active Python asset would violate the Stage 11 cutover gates.
