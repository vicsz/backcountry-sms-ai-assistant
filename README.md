# Backcountry SMS AI Assistant

> A low-bandwidth, SMS-first AWS assistant for practical backcountry questions—and a working
> example of how to take a GenAI idea through architecture, implementation, evaluation, safety,
> observability, and cost-aware operation.

Built by [Victor Szoltysek](https://www.linkedin.com/in/victorszoltysek/), Principal AI & Cloud
Architect.

## Why I built it

The idea started in Summer 2026 after six days canoeing and portaging in Algonquin Park, hours from
civilization and with no cellular service at all. Trip planning is continuous out there: how long
will the next hop between camps take, will the rain change the route, is a fire ban in effect, and
did the team win last night? Useful information should not require finding a signal, opening an
app, and reconstructing a full online workflow.

Apple Messages via satellite makes a short-message interface increasingly practical. The phone can
exchange a small SMS where the feature is available; the system on the other end still has to
resolve places, retrieve current weather and operational data, search stable park information, and
turn the result into a concise answer.

That makes this an AI application engineering problem, not just a chatbot prompt. The model
interprets ambiguous human questions and composes the answer; deterministic code, authoritative
sources, retention controls, failure handling, and evaluations make the result useful.

On supported iPhones, Messages via satellite can exchange small messages when cellular and Wi-Fi
are unavailable, subject to device, carrier, regional, and environmental conditions. This project
provides the ordinary SMS destination on the other end. See [Apple's Canadian satellite guidance](https://support.apple.com/en-ca/105097)
and [Messages via satellite documentation](https://support.apple.com/en-euro/guide/iphone/iphb9262f4dd/ios).

## Architecture

![Backcountry SMS AI Assistant AWS architecture](aws-architecture.png)

The deployed core is a two-way SMS flow: satellite-enabled iPhone Messages reach AWS End User
Messaging SMS, which publishes an inbound notification to Amazon SNS and invokes the Rust Lambda
orchestrator. The Python CDK remains the infrastructure deployment path. Rust uses short-lived
DynamoDB SMS thread context, provider lookups, and Amazon Bedrock, then sends the reply directly
through the AWS End User Messaging SMS API.

The source-backed extensions add an Amazon Bedrock Knowledge Base backed by an Amazon S3 Vectors
vector database over an S3-curated Ontario Parks corpus, plus versioned S3 fire-ban snapshots
queried through Amazon Athena for geospatial lookups.

The Ontario Parks Knowledge Base, S3 Vectors, and one-time snapshot ingestion are deployed on the
Demo target. Their freshness/source-date contract and recurring refresh remain deferred. The
fire-ban S3/Athena ingestion path remains local/proposed pending its own live-ingestion gate. SNS
is used for inbound notification; outbound SMS is sent directly by Lambda through the AWS End User
Messaging SMS API.

## How I built it

This project was developed as a personal AI application engineering exercise using specification-
driven development with Codex on a personal ChatGPT Plus plan. The efficient Luna model was the
main model used for implementation and review. I also made heavy use of GPT-Live-1 voice
conversations and ChatGPT iOS remote access to reason through designs and monitor delegated jobs.

The workflow is deliberately structured: define one bounded specification, implement it, test it,
perform an independent review, run the applicable validation gate, and then perform explicit
deployment or live verification.

> **GPT-5.6 Luna was surprisingly capable.** It did most of the implementation and review work for
> this project when paired with a clear specification, structured workflow, and validation gates.

> **GPT-Live-1 was useful as a back-and-forth thinking partner.** I used it extensively for
> brainstorming and exploring ideas while away from the desk, including while biking to work.
> ChatGPT's CarPlay support made that kind of hands-free conversation more useful on the move.

> **ChatGPT Remote on iOS was also extremely useful.** It let me kick off long-running
> specification implementations, then monitor and guide the agents while away from the desk.

## Technical snapshot

Python, AWS CDK, AWS Lambda, Amazon SNS, AWS End User Messaging SMS, DynamoDB, Amazon Bedrock,
Amazon Bedrock Knowledge Bases, Amazon S3, S3 Vectors vector database, RAG, Athena, CloudWatch,
X-Ray, pytest, Ruff, mypy, and CI/CD.

## Example interaction

These are synthetic examples showing the intended shape of the user experience:

```text
User:  What's the weather at Burnt Island Lake tomorrow?
Bot:   Burnt Island Lake: 12 C tomorrow, 60% chance of rain, gusts up to 28 km/h. Pack rain gear.
```

```text
User:  What should I know before visiting Algonquin?
Bot:   The park guide covers access, facilities, camping areas, and trip-planning context.
       Current fire-ban status: a fire ban is in effect.
```

The assistant is intentionally concise: the SMS boundary is part of the product design.

## What the project demonstrates

The LLM is not the system of record. Deterministic code owns authoritative lookups, coordinates,
source boundaries, output limits, and failure behavior. The project demonstrates:

- two Bedrock calls for a typical weather request: intent/context extraction, then answer synthesis;
- deterministic code for facts, coordinates, source precedence, output limits, and fallbacks;
- short-lived SMS thread context in DynamoDB;
- RAG through an Amazon Bedrock Knowledge Base for stable Ontario Parks information;
- S3 and Athena for versioned fire-ban and geospatial data;
- automated tests, provider evaluations, model evaluations, and LLM-as-judge assessment;
- application guardrails, observability, tracing, performance measurement, and cost-aware design.

## Evaluation and testing

The project treats evaluation as a release concern, not a final demo flourish. Deterministic tests
cover schemas, location precedence, coordinates, model-call counts, SMS length, redaction, and
offline behavior. Model and provider evaluations cover interpretation, history use, location
extraction, ambiguity, candidate ranking, and bounded responses. LLM-as-judge adds qualitative
signal, but cannot override deterministic safety, privacy, schema, coordinate, call-count, or SMS
failures. Live provider checks remain explicit and separate from ordinary CI.

## Model, performance, and cost decisions

The Demo target currently uses Amazon Nova Micro for its bounded capture/live checks. Nova 2 Lite
remains the non-test CDK default, but this repository has no deployed production environment.
Nova Micro was compared through a separate test path and was faster in the observed sample; the
model choice remains environment-specific rather than a production migration claim.

At approximately 100 short interactions per month, the variable AI and serverless workload is
small. Total cost still depends on SMS origination/delivery, weather and location providers,
logging, and any Knowledge Base or Athena usage.

> **The cost lesson is not simply “pick the cheapest model.”** SMS, provider usage, observability,
> quotas, and operational limits all shape the real user experience.

See the detailed [performance findings](docs/performance.md).

## Current status

The core SMS, weather, context, observability, tracing, reliability, performance, evaluation, and
carrier-independent test paths are deployed and verified. The Ontario Parks RAG snapshot is
deployed and read-only verified, while fire-ban/geospatial ingestion remains deferred and the RAG
freshness/source-date contract is not implemented. The current assistant is allow-listed and
intentionally narrow.

## Further reading

- [Measured performance findings](docs/performance.md)
- [Development workflow](development-workflow.md)
- [Evaluation harness](specs/stage-7-evaluation-harness.md)
- [Ontario Parks RAG specification](specs/stage-9.3.2-ontario-parks-rag-mvp.md)
