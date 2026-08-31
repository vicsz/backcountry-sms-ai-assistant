# Idea backlog

This is a lightweight backlog for useful ideas that are not ready to become project work. Nothing
here is committed scope, a stage, or an implementation promise.

When an idea becomes worth pursuing, turn it into one bounded spec under `specs/` with acceptance
criteria and non-goals. Otherwise, leave it here, revise it, or remove it. Keep the list useful and
lightweight; it is not a second project plan.

## Seeds

### IDEA-001 — GitHub Actions CI/CD and deployment traceability

Status: Seed

Explore proper CI/CD integration, including:

- GitHub Actions setup.
- OIDC from GitHub Actions to AWS.
- CI build and validation.
- CD deployment, possibly from a release branch.
- A test harness that can produce a useful, visually clear report.
- Artifact versioning, perhaps with an incrementing build number.
- An easy way to identify what artifact/version is deployed.

Current boundary: the repository already has local CI checks for Ruff, unit tests, and `cdk synth`.
This seed is about the missing GitHub workflow, deployment path, release policy, reporting, and
deployed-version traceability.

### IDEA-002 — Externalized configuration

Status: Seed

Explore moving appropriate runtime configuration outside the code and deployment package, for
example through AWS Config or Parameter Store.

The eventual spec would need to decide which values are configuration, who may change them, how
changes are validated, and how configuration versions are tied to a deployment.

### IDEA-003 — Architecture and design documentation

Status: Seed

Create a written architecture/design package with AWS architecture diagrams and explanations of
the major boundaries and flows.

### IDEA-004 — AI Gateway boundary

Status: Seed

Explore an AI Gateway abstraction, either as a project-level abstraction or as a real gateway
component. Keep the choice open until the required boundary, value, and operational cost are
clear.

### IDEA-005 — LLM input and output guardrails

Status: Seed

Explore guardrails on both incoming user input and generated output, including the appropriate
AWS or application-level control boundary.

### IDEA-006 — Abuse prevention and throttling

Status: Seed

Explore throttling and related abuse-prevention controls for the SMS/LLM path.

### IDEA-007 — Opt-in and user-management flow

Status: Seed

Define how new people are added to the system and how the opt-in mechanism and flow should work.

### IDEA-008 — More static typing in Python

Status: Seed

Explore refactoring the Python code toward stronger static typing.

### IDEA-009 — Preserved user context and inferred preferences

Status: Seed

Explore richer user context so the LLM receives the current message, a bounded set of recent
messages, and user information. Consider whether useful information such as travel preferences
can be preserved automatically rather than only through explicit user input.

Current boundary: Stage 5 already implements a short-lived, bounded message context window. This
seed is about any additional durable or inferred context beyond that existing contract.

### IDEA-010 — Basic internet lookups

Status: Seed

Explore allowing simple, bounded internet lookups for current-fact questions such as:

- Checking what time Portage Store closes.
- Checking the score of a game today.
- Checking the latest status of a SpaceX Starship launch.

The eventual spec would need to define the allowed lookup scope, source handling, timeouts,
response limits, and how uncertain or stale results are communicated over SMS.

### IDEA-011 — Semantic evaluation with embeddings

Status: Seed

Explore semantic-based evaluations using embeddings to compare generated responses with expected
or reference outcomes.

This may be overkill for the product’s actual needs, but could make a strong evaluation and demo
capability. The eventual spec would need to establish whether semantic similarity adds meaningful
signal beyond the existing deterministic checks and rubric-based evaluation.

### IDEA-012 — Dead-message handling at both ends

Status: Seed

Explore dead-letter or dead-message queues at both ends of the messaging flow, with metrics and
operational observability around failed, retried, and abandoned messages.

The eventual spec would need to identify the two boundaries, define retry and retention behavior,
avoid duplicate SMS sends, and specify the dashboards, alerts, and redacted evidence needed to
investigate failures.
