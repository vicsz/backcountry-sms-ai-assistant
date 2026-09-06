# ENH-0010 — Public repository release hygiene

**Status:** Implemented; publication decision remains separate.

## Objective

Make the repository's public-facing material accurate, privacy-safe, and clear about the boundary
between deployed Demo behavior, local experiments, proposed future targets, and deferred ingestion.

## Audit findings addressed

- The README no longer presents a fire-ban result as a current example while live ingestion is
  deferred.
- Fire-ban and geospatial capabilities are described as local/proposed where they are not live.
- The README no longer includes unnecessary personal AI-tooling and account-plan commentary.
- Older specifications explicitly identify `production` as a future target; the deployed target
  remains Demo.
- The duplicate sentence in `docs/testing.md` is corrected.
- The stale, unreferenced root PNG architecture diagram is removed; `docs/aws-architecture.svg` is
  the current architecture artifact.
- Generated artifacts, local working material, credentials, private-key material, and
  account-specific deployment output remain ignored or untracked.

## Scope

- Update README and public documentation for truthful deployment and freshness claims.
- Preserve synthetic examples and existing author attribution.
- Record the audit boundary and remaining publication decisions.

## Non-goals

- Do not publish, create a release, rewrite Git history, or change repository visibility.
- Do not choose a software license on the author's behalf.
- Do not remove useful technical specifications merely because they describe a future target.
- Do not change runtime, infrastructure, deployment, or CI behavior.

## Acceptance criteria

1. Public documentation does not imply that fire-ban ingestion or RAG freshness is live.
2. Public documentation distinguishes the deployed Demo target from the undeployed Production
   vocabulary.
3. Targeted current-tree and history scans find no credential, PEM private-key, account-specific
   ARN, raw SMS, or non-synthetic phone-number pattern. A dedicated secret scanner was not
   installed in the repository environment, so a final publication pass should still run one.
4. Generated output and local/private working paths are not tracked.
5. The remaining publication decisions are explicit: license selection, dedicated final history
   scan, and whether personal attribution remains as written.
6. Documentation diff checks pass and no runtime files are changed.
