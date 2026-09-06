# ENH-0008 — Retire the legacy Python context table safely

**Status:** Implemented; physical table was retained and detached from CDK ownership.

## Objective

Remove the unused Python-era `MessageContext` table from active CDK ownership without deleting its
existing data. The deployed Rust request path uses `RustCandidateMessageContext`; no runtime code
references the historical table.

## Scope

- Apply `RemovalPolicy.RETAIN` to the existing historical table before detaching it from the CDK
  template.
- Deploy that policy update to the Demo stack.
- Remove the historical table definition from the CDK template in the follow-up phase.
- Verify that CloudFormation no longer manages the resource while the physical table remains
  available for a separately authorized retention/deletion decision.

## Non-goals

- Do not read, export, or delete table contents in this enhancement.
- Do not change the Rust context table, TTL behavior, or request path.
- Do not delete the retained physical table without a separate explicit decision after reviewing
  its 30 existing items.

## Acceptance criteria

1. The historical table has a retain deletion policy before CDK detachment.
2. The Rust runtime and its context table remain unchanged.
3. The final synthesized template contains no legacy `MessageContext` table.
4. CloudFormation reports the legacy resource as retained/detached after the follow-up deployment,
   and the physical table remains available.
5. Tests verify the phase-1 retain policy and the deployed Rust subscription remains unchanged.
