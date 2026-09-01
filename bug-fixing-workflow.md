# Bug-fixing workflow

This workflow applies when a request reports existing behavior as broken, failing, incorrect, or
regressed, or asks to fix a behavior. It complements the spec-first development workflow: a spec
describes intended new behavior, while a bug record preserves how existing behavior deviated from
that expectation.

The project-local `.codex/skills/bug-fixing-workflow/SKILL.md` helps route matching requests into
this workflow automatically. The repository instructions and this document remain authoritative.

## Intake and tracking

1. Search `bugs/INDEX.md` and the files under `bugs/` for an existing matching bug.
2. Update the existing record, or create the next `BUG-####-short-title.md` from `bugs/TEMPLATE.md`.
3. Set the status to `Open` and preserve the original report and evidence without silently
   rewriting it.
4. Keep private screenshots, raw SMS, transcripts, phone numbers, coordinates, credentials,
   provider payloads, and account-specific details out of committed records. Use ignored local
   evidence when necessary and record only a safe description or reference.

Use `python3 scripts/next_bug_id.py` to print the next available ID. The helper is read-only; the
bug file and `bugs/INDEX.md` are created or updated explicitly and reviewed like any other change.

## Investigation and implementation

1. Move the record to `Investigating`.
2. Reproduce the defect with the smallest useful fixture, test, command, or evidence review.
3. Record observed facts separately from hypotheses, then document the confirmed or best-supported
   root cause and its confidence.
4. Define the smallest fix and explicit non-goals before changing code or configuration.
5. Add an automated regression test that would fail for the reported defect and passes after the
   fix. Do not rely only on a manual reproduction.
6. Use the existing `Backcountry Implementer` and `Backcountry Reviewer` roles when delegation is
   used. The implementer does not deploy, send SMS, or commit; the reviewer is read-only.

## Verification and closure

Run focused checks while iterating. After review and the final focused fix, run the applicable
final validation gate from `development-workflow.md` exactly once.

Provider, Bedrock, Lambda, SNS, SMS, or other deployed-runtime defects require the smallest
explicit live check after review. Keep live evidence separate from local test evidence; never hide
live calls, deployments, or SMS sends in ordinary tests or hooks.

Before commit, update the bug record and register with the cause, fix, regression tests, validation
results, and current live-verification state. Record the commit after it exists.

Use these statuses:

- `Open` — reported and registered, not yet investigated.
- `Investigating` — reproduction or cause analysis is in progress.
- `Fixed Locally` — fix and automated regression coverage pass locally.
- `Awaiting Live Verification` — local work passes but required deployed/provider verification is
  outstanding.
- `Closed` — automated validation and all required live verification are complete.

If live verification is not required, a bug may move from `Fixed Locally` to `Closed` after the
documented local validation gate. Do not claim deployed behavior from offline tests alone.
