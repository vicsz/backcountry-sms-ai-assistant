# Backcountry SMS AI Assistant

> A deployed Rust/AWS GenAI assistant for constrained backcountry questions over SMS, with
> grounded retrieval, deterministic provider lookups, and explicit safety boundaries.

Built by [Victor Szoltysek](https://www.linkedin.com/in/victorszoltysek/), Principal AI & Cloud
Architect.

![Backcountry SMS AI Assistant AWS architecture](aws-architecture.png)

## What this demonstrates

This is an AI application engineering portfolio piece: taking an ambiguous, low-bandwidth use
case from idea to a bounded, measured AWS system.

- Rust Lambda is the deployed request runtime; Python CDK remains the infrastructure path.
- AWS End User Messaging SMS, SNS, DynamoDB, Bedrock, weather/location providers, and observability
  form the request path shown above.
- Deterministic code owns authoritative facts, coordinates, source boundaries, SMS limits, privacy,
  and failure behavior. The LLM interprets and synthesizes; it is not the system of record.
- Stable Ontario Parks information uses bounded RAG through an Amazon Bedrock Knowledge Base,
  with local retrieval experiments and evaluation evidence retained separately.
- Specifications, independent review, CI gates, provider/model evaluations, performance measurement,
  and cost boundaries are part of the implementation—not an after-the-fact demo checklist.

## Why I built it

The idea came from a six-day canoeing and portaging trip in Algonquin Park, where useful answers
cannot depend on a full online workflow. The interesting problem is not “add a chatbot”; it is
making a small AI system useful when connectivity, message length, data freshness, and safety all
matter.

## Evidence

- [Testing and evaluation](docs/testing.md) — deterministic, provider, model, and offline gates.
- [RAG tuning report](docs/rag-tuning-report.md) — corpus profile, section-first chunking, local
  semantic retrieval, hybrid comparison, and golden-query results.
- [Performance findings](docs/performance.md) — measured latency, cold-start, package, memory, and
  cost observations.
- [Current status](STATUS.md) — deployed Demo evidence and explicitly deferred work.
- [Rust runtime contracts](rust/README.md) — the request-path implementation and test ownership.

## Typical request path

An inbound SMS is normalized and interpreted, authoritative provider data is retrieved
deterministically, stable guide content is retrieved with bounded context, and Bedrock synthesizes
a concise response. The reply is sent directly through the AWS End User Messaging SMS API. The
SMS boundary is part of the product design, not merely an output-format constraint.

## Scope and status

The deployed Demo target includes the two-way SMS path, Rust runtime, weather, short-lived context,
observability/tracing, and a read-only Ontario Parks RAG snapshot. Fire-ban ingestion and RAG
freshness/refresh remain intentionally deferred. This repository does not claim a production
environment.

## Model and operating decisions

The Demo uses Amazon Nova Micro for bounded capture/live checks; model choice remains environment-
specific rather than a production migration claim. The project measures the full operating shape:
SMS and provider usage, model calls, logging, retrieval, cold starts, memory, package size, and
failure behavior—not just token cost.

The core design principle is simple: use the model for interpretation and synthesis, and use
deterministic systems for facts, constraints, and safety.
