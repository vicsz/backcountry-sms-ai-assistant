# Stage 9.3 — Camping retrieval knowledge base

Status: Proposed; follows Stage 9.2 and 9.2.1

## Objective

Add a cheap, bounded retrieval path for curated camping knowledge. The Ontario provincial parks
corpus and its one-time RAG integration are split into:

1. `specs/stage-9.3.1-ontario-parks-guide-corpus.md` — generate one source-linked Markdown file.
2. `specs/stage-9.3.2-ontario-parks-rag-mvp.md` — load that file once and implement bounded
   retrieval and handler behavior.

Future camping corpora remain provisional and require separate scope, source, and cost decisions.

## Scope and content boundary

- Start with the all-Ontario provincial-parks guide defined by the two child specs. Practical trip
  planning, equipment, low-risk skills, and leave-no-trace guidance require a later corpus decision.
- Keep current fire bans, closures, and other time-sensitive legal or operational status outside RAG;
  Stage 9.2 owns that data.
- Bound retrieval to a small number of relevant chunks, strict time/token limits, and one concise
  SMS response. If evidence is absent, weak, stale, or conflicting, say so.
- Preserve citations/source labels and distinguish source fact from advice.

## Future ingestion boundary

Scheduled refresh, source polling, automated re-ingestion, last-known-good promotion, and corpus
history are intentionally deferred. They require a future spec after the one-time corpus and RAG
MVP demonstrate useful retrieval and an acceptable cost.

## Cost and operational controls

Prefer serverless/managed components, one-time corpus loading, bounded retrieval, short prompts, and
the smallest capable model. For the Ontario parks MVP, the selected implementation is Bedrock
Knowledge Bases with the configuration in `stage-9.3.2-ontario-parks-rag-mvp.md`; a low-cost
alternative and any always-on database are deferred. Track retrieval, model, storage, and failure
costs during the explicit live proof.

## Tests and live gates

Offline tests cover corpus validation, metadata/citation preservation, chunking, retrieval limits,
empty/irrelevant results, failure behavior, and exclusion of current fire-ban/closure content.
Evaluation covers common and unsupported questions, conflicts, and citation correctness; retrieved
camping guidance must not establish a current ban or closure.

Any live ingestion/retrieval check is opt-in, separate from CI, uses non-sensitive fixtures, records
redacted evidence and cost, and never deploys or sends SMS as a hidden side effect.

## Acceptance criteria and non-goals

After the two child specs, document any future corpus recommendation, cost bound, refresh/audit
design, and citation contract. This umbrella spec does not authorize live SMS, legal-status lookup,
or hidden live calls; one-time AWS setup and an explicit redacted smoke test follow the child-spec
gates.
