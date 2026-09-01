---
name: bug-fixing-workflow
description: Track and resolve reported software bugs, regressions, broken behavior, or failing behavior with preserved evidence, root-cause analysis, regression tests, and explicit verification.
---

# Bug-fixing workflow

Use this skill when the user reports existing behavior as broken, failing, incorrect, or regressed,
or asks to fix a behavior. Do not use it for ordinary feature work unless the user identifies a
defect in existing behavior.

## Required intake

Before changing implementation files:

1. Inspect the repository instructions and locate its bug register, records, and workflow.
2. Search the register and records for an existing matching bug.
3. Update the matching record, or create the next numbered record from the repository template.
4. Preserve the user's original report and evidence. Do not silently rewrite source material.

If the repository has no bug-tracking convention, establish the smallest explicit record in the
project's documentation area before implementation and state that assumption to the user.

Keep screenshots, raw messages, transcripts, phone numbers, coordinates, credentials, private URLs,
provider payloads, and account-specific details out of committed records. Use ignored local evidence
when needed and record only a safe description or reference.

## Investigation through closure

Guide the task through these states:

- Open: registered but not investigated.
- Investigating: reproduction or cause analysis is active.
- Fixed Locally: the fix and automated regression coverage pass locally.
- Awaiting Live Verification: required deployed/provider verification remains.
- Closed: automated validation and all required live verification are complete.

Reproduce the defect with the smallest useful test, fixture, command, or evidence review. Record
observed facts separately from hypotheses, then document the root cause and confidence before fixing.
Implement the smallest scoped change, with explicit non-goals, and add an automated regression test
that would fail for the reported behavior.

Before commit, update the bug record and any project index with the cause, fix, regression tests,
validation results, and live-verification state. Do not claim deployed behavior from offline tests.
Provider, model, deployment, messaging, or other external-runtime defects require an explicit,
authorized live check after review. Never hide deployments, external calls, or messages in ordinary
tests or hooks.

Defer to repository-specific review, validation, privacy, deployment, and commit instructions. The
skill does not authorize commits, pushes, deployments, or external communication.

When the repository defines environment targets, use its terminology for live verification. Do not
assume that “live” means production or that a configured production target is deployed. Regression
tests should include the bug ID in the test name or a `Regression: BUG-####` docstring/comment, and
the bug record should list exact `path::test_name` references. Broader model/provider eval cases
should use a related bug-linked case ID and remain distinct from deterministic unit tests.
