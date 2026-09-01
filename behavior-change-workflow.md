# Behavior-change workflow

This is the shared lifecycle for work that changes or evaluates assistant behavior. It keeps
exploratory findings, defects, planned enhancements, and specification changes distinct while
using the same disciplined delivery loop.

The work type is decided after the initial analysis; an exploratory test result is not
automatically a bug.

## Classify the finding

Use the narrowest accurate classification:

- **Bug (`BUG-####`)** — an existing, promised, or safety-required behavior is broken, regressed,
  incorrect, or unsafe.
- **Enhancement (`ENH-####`)** — useful new capability that was not previously implemented or
  promised.
- **Spec gap (`SPEC-<stage>`)** — the intended behavior or acceptance boundary is unclear and
  must be defined before implementation.
- **Expected limitation** — the assistant correctly declines, qualifies, or asks for information
  because the capability is outside the current contract.

Use “capability finding” as a neutral label while an exploratory sanity test is being assessed.
Record exploratory ideas in [`docs/ideas.md`](docs/ideas.md) until they become a bounded work
item. Do not relabel an enhancement as a bug merely because the capability would be useful.

## Shared delivery loop

1. Capture the observed message, result, context, and safe evidence. Do not commit private
   screenshots, raw SMS, phone numbers, coordinates, production payloads, or secrets.
2. Search existing records, specs, and the ideas backlog for a matching item.
3. Reproduce or characterize the behavior with the smallest useful fixture, test, eval, or
   evidence review.
4. Classify the finding and record the expected behavior, scope, non-goals, and acceptance
   criteria before implementation.
5. Implement the smallest scoped change.
6. Add automated coverage linked to the work identifier.
7. Use the implementer/reviewer pattern and run the applicable validation gate.
8. Perform explicit deployed/provider verification when the change affects Bedrock, providers,
   Lambda, SNS, SMS, or other deployed runtime behavior.
9. Update the record, spec, index, and `STATUS.md` as applicable before committing.
10. Commit with the work identifier at the start of the message.

Every user-facing reply must fit one SMS segment: 160 GSM-7 septets. Weather advice should target
140 characters when deterministic fire-status text may also be appended. Tests and evaluations
must check the actual bounded output, not just the model prompt or an unbounded draft.

## Testing language and traceability

All behavior-changing work needs automated coverage when a deterministic test is feasible:

- A bug uses a **regression test** proving the reported failure does not return.
- An enhancement uses an **acceptance or capability test** proving the new behavior.
- A spec gap uses **spec acceptance tests** proving the newly defined contract.

Name or annotate tests with the identifier, for example:

```text
BUG-0002-CROSSING-001
ENH-0001-TARP-001
```

The test record should link to the exact `path::test_name` or eval case. A model/provider eval is
useful for broader behavior coverage, but does not replace a deterministic regression test when
one is feasible.

## Routing rules

- Existing broken or failing behavior: follow [`bug-fixing-workflow.md`](bug-fixing-workflow.md).
- New capability or small behavior improvement: create a bounded record under `enhancements/` or
  a spec under `specs/`, then follow this shared loop and the normal development workflow.
- Ambiguous desired behavior: clarify the contract in a spec amendment before implementation.
- Unsupported current facts or safety-sensitive claims: treat fabricated or overconfident output
  as a bug; treat an honest bounded refusal as expected behavior or a feature request.

The repository’s `AGENTS.md` and the selected record/spec remain authoritative. This document does
not authorize commits, pushes, deployments, provider calls, or SMS sends.
