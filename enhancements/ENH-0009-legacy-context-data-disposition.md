# ENH-0009 — Dispose of retained legacy context data

**Status:** Review gate passed; deletion authorized and pending execution.

## Objective

Delete the detached Python-era context table after confirming that the deployed Rust runtime and
CDK no longer use it, and that no backup or retention dependency requires preserving it.

## Review evidence

- No active application or CDK references to the historical `MessageContext` table remain.
- CloudFormation no longer manages the table; the previous detach reported `DELETE_SKIPPED`.
- Metadata-only inspection found an `ACTIVE` table with 30 items and approximately 8.9 KB of data.
- Point-in-time recovery is disabled and no on-demand DynamoDB backups were listed.
- No message bodies, phone values, or table contents were read or exported during the review.

## Scope

- Delete only the exact retained physical table identified during the review.
- Verify that the table is gone and that the Rust context table remains managed and unchanged.
- Update the status ledger and retain this evidence as the deletion record.

## Non-goals

- Do not export, snapshot, or copy the retained message data.
- Do not change the Rust context table, runtime, IAM, or CDK deployment topology.
- Do not delete any other table, backup, log group, bucket, vector index, or provider data.

## Acceptance criteria

1. The exact retained legacy table is deleted only after the metadata-only review gate passes.
2. A follow-up metadata check reports that the table no longer exists.
3. CloudFormation still has no legacy table resource and the Rust context table remains present.
4. Rust contract tests, targeted Python/CDK checks, and `git diff --check` pass.
5. The repository records that the deletion was completed without retaining an exported copy.
