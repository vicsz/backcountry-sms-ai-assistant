# Stage 11 Rust runtime slice

This directory contains the Rust request runtime for the Stage 11 migration. The `bootstrap`
binary uses the AWS Lambda Rust runtime and the deterministic orchestration plus concrete AWS/HTTP
adapters implement:

- nested SNS/provider event parsing;
- allow-list normalization and fail-closed delivery configuration;
- strict typed interpretation validation;
- GSM-7 normalization, septet counting, and one-segment bounding;
- deterministic general/weather/information-lookup/fire-status routing;
- retrieval citation and grounding guards;
- fire-ban snapshot freshness and validated WKT polygon/multipolygon membership;
- side-effect adapter traits, bounded timeout/retry configuration, warm-process client reuse, and
  deterministic fakes;
- Bedrock Converse, Bedrock Knowledge Base retrieval, DynamoDB, Amazon Location Places, Open-Meteo,
  and AWS End User Messaging SMS adapters;
- redacted low-cardinality JSON/CloudWatch EMF telemetry.

The local capture harness injects deterministic fakes and records logical calls. It does not call
Bedrock, HTTP providers, DynamoDB, retrieval, Athena, SNS, or SMS. The deployed Demo request path
is now the Rust Lambda; the retained Python modules are support/evaluation code and are not
deployed as a request runtime. Fire-ban ingestion is explicitly deferred; Rust reports unknown
with `ingestion_deferred` rather than claiming live status.

## Local checks

From this directory:

```text
make fmt
make test
make clippy
make package
```

The Lambda package target is `x86_64-unknown-linux-gnu`, matching the existing CDK default
architecture. `rust-toolchain.toml` pins the compiler and target. `make package` creates the
reproducible locked release package at `target/package/backcountry-rust-runtime.zip` and the CDK candidate
asset at `dist/bootstrap`. On Apple Silicon, a Linux cross-linker such as Zig may be required;
the package can be built with `BUILD_CMD='cargo zigbuild' make package` when
`cargo-zigbuild` is installed.

The Python CDK remains the infrastructure deployment path. The Demo test stack defaults to the Rust
request Lambda and points inbound SNS at it. `rust_runtime=false` is the explicit Python rollback
path. Setting `rust_candidate=true` instead adds an isolated `provided.al2023` candidate function;
it is capture-only, has no inbound SNS subscription, uses a separate context table, and has no SMS
permission. The Stage 11 specification records the completed parity, capture, measurement, review,
rollback, and cutover gates.
