# Stage 9.3.3 — Knowledge Base retrieval and chunking tuning

Status: Partially implemented — offline evaluation capability

## Objective

Evaluate whether the Stage 9.3.2 Bedrock Knowledge Base configuration retrieves the right
Ontario Parks evidence for bounded park-information questions, and select a safer retrieval and
chunking configuration only if it improves measured evidence coverage without violating the
existing citation, current-status, latency, cost, context, and one-segment SMS boundaries.

This stage produces a reproducible offline evaluation report and, only when explicitly authorized,
a separate live-retrieval report. It does not presume that a better-scoring variant is safe to
deploy: retrieval quality and generated answer quality must be measured independently.

## Scope

- Evaluate the existing one-time `data/rag/ontario-provincial-parks-guide.md` corpus and the
  Stage 9.3.2 Knowledge Base baseline: Titan Text Embeddings V2, fixed 300-token chunks, 30-token
  overlap, and bounded top-k retrieval.
- Compare bounded fixed-size chunking variants and a heading-aware variant that keeps a park
  section and its subsection heading together where practical.
- Measure retrieval evidence recall/precision, score distributions, latency, estimated provider
  cost, citation correctness, answer grounding, and negative/current-status behavior.
- Use a fixed golden question/evidence set, fixed query and prompt settings per experiment, and
  redacted artifacts that contain no raw user or provider payloads.
- Record a recommendation to retain, tune, or reject a candidate, with explicit rollout gates.

## Explicit non-goals

- No corpus refresh, source re-download, park-page scraping, normalization change, or content
  correction.
- No ingestion automation, scheduled sync, source polling, refresh job, or production data-source
  mutation.
- No change to handler routing, response prompts, SMS formatting, live status providers, or
  unrelated infrastructure.
- No live SMS, production traffic, deployment, or provider call hidden in tests or CI. Offline
  fixtures must run without AWS calls. Any AWS retrieval/ingestion experiment is a separately
  authorized, visible live check with a separate report and must not be described as offline evidence.
- No claim that this evaluation establishes current fire-ban, closure, opening, reservation,
  availability, weather, fee, or route status.

## Golden question and evidence set

The fixture must contain the question, intent, expected evidence IDs, acceptable answer claims,
required citation metadata, and whether the query is supported, negative, or current-status. Gold
labels are reviewed before experiments begin and are not changed to fit a result.

Use a stable JSON shape for each case:

```json
{
  "case_id": "algonquin.activities.001",
  "question": "What activities does Algonquin list?",
  "class": "supported",
  "gold_evidence": ["algonquin.activities", "algonquin.facilities"],
  "acceptable_claims": ["canoeing", "backcountry camping"],
  "required_citation": {"park": "Algonquin Provincial Park", "sections": ["Activities"]}
}
```

An evidence item is relevant when it directly supports at least one expected claim or the
required current-status/unsupported conclusion. Partially relevant means it supports the park or
topic but not the claim; count it separately and do not treat it as fully relevant for precision.
Unrelated chunks are non-relevant. Negative and current-status cases have an empty
`gold_evidence` list unless the expected result is a deterministic live-boundary redirect.

| Case | Question shape | Required evaluation boundary |
| --- | --- | --- |
| Algonquin | “What should I know before visiting Algonquin based on the guide?” | Retrieve Algonquin park facts and headings; do not treat guide text as current operations. |
| Killarney | “Does Killarney have backcountry camping?” | Retrieve the Killarney camping evidence and cite the park/section. |
| Arrowhead | “What facilities are listed for Arrowhead?” | Retrieve only listed facilities; penalize invented amenities. |
| Canoeing comparison | “Which Ontario parks mention canoeing and boat launches?” | Recall each gold-supported park/claim and avoid unsupported matches. |
| Rental terminology | “Where can I rent a canoe?” | Test the relevant rental evidence, including the exact heading/label `Rentals - Canoe`; do not equate a generic boat launch with a rental. |
| Unsupported fact | “What are the hours and prices at the Portage Store?” | Return insufficient/unsupported evidence; never invent Portage Store facts or cite an unrelated park section. |
| Negative park | “Does NeverListed Park have winter camping?” | Return bounded uncertainty; no fabricated park or camping attribute. |
| Current status | “Is Algonquin under a fire ban today?” | Route to the live fire-status boundary or redirect; never answer from the static corpus. |
| Current operations | “Is the park open tomorrow and are sites available?” | Redirect or return `unclear`; no RAG-derived operating or availability claim. |

Include paraphrases and at least one multi-park query, while preserving the same gold evidence
labels. Tests must include empty, irrelevant, conflicting, and low-score retrieval results.

## Independent evaluation protocol

Run two offline stages with separate labels and outputs, plus an optional live stage:

1. Retrieval evaluation sends each supported or negative-evidence question to the candidate
   retriever only. Current-status cases are evaluated first by the routing boundary and must not
   invoke the retriever. For retrieved cases, measure whether the expected evidence chunks, park,
   heading, and claim-bearing sections appear in top-k. Do not use the answer generator to decide
   whether retrieval succeeded.
2. Offline generation evaluation receives only fixture excerpts and safe citation
   metadata. It measures groundedness, completeness against the gold claims, citation accuracy,
   unsupported-claim rate, and correct refusal/redirect behavior. A good generated answer cannot
   rescue missing retrieval evidence; retrieval misses remain misses.
3. Optional live retrieval/generation evaluation repeats the same cases against the deployed
   Knowledge Base only after explicit authorization. Store aggregate scores, latency, and cost in
   a separate live report; never combine them with offline pass/fail evidence.

Use deterministic model/settings where available, otherwise record model ID, temperature and
seed (or state that they are unavailable), prompt/template version, corpus SHA-256, embedding
model, region, candidate settings, and run timestamp. Human review or a deterministic rubric must
label borderline grounding and citation cases; automated scores alone do not authorize rollout.

## Candidate chunking and retrieval matrix

The baseline is fixed 300 tokens with 30-token overlap and the existing bounded top-k. Test fixed
variants at 200/20, 300/30, and 500/50 tokens, plus a heading-aware park-section variant. The
heading-aware variant must retain the park name and subsection heading (for example, activities,
facilities, camping, or `Rentals - Canoe`) with the smallest useful adjoining text, while applying
an explicit maximum chunk size and preserving source metadata. Do not introduce semantic
chunking, corpus edits, or an unbounded context window.

For every chunking candidate, test top-k values 1, 3, and 5, or the smallest supported equivalent.
The matrix must record:

| Dimension | Values |
| --- | --- |
| Chunking | baseline fixed 300/30; fixed 200/20; fixed 500/50; heading-aware park sections |
| Retrieval top-k | 1, 3, 5 |
| Query set | full golden set, with supported, negative, and current-status subsets |
| Generation | one fixed bounded response configuration, held constant across candidates |

Do not select a winner on aggregate recall alone. Inspect failures by park, heading, question
type, exact rental terminology, unsupported Portage Store facts, and current-status boundary.

## Metrics and pre-registered thresholds

Before any experiment, choose and record numeric acceptance thresholds in the report header. The
experiment runner must fail or mark the run inconclusive when thresholds are absent. At minimum,
pre-register:

- retrieval evidence recall@k: proportion of gold evidence items present in top-k;
- retrieval precision@k: proportion of returned chunks judged relevant to the question;
- park/section recall: whether the correct park and claim-bearing heading are retrieved;
- unsupported-evidence exclusion: proportion of unsupported questions for which no unrelated
  chunk is incorrectly treated as answer-bearing evidence;
- current-status routing: proportion of current-status questions that avoid RAG and use the
  appropriate live boundary;
- refusal correctness: proportion of unsupported/current-status cases receiving the required
  bounded uncertainty or redirect response;
- citation accuracy and citation completeness for generated answers;
- groundedness and unsupported-claim rate;
- p50/p95 retrieval latency and end-to-end generation latency;
- estimated per-question and per-evaluation-run cost, with embedding/ingestion and generation
  components separated where measurable.

The experiment owner must record thresholds in the report header before the first candidate
retrieval or generation run. Set them from the Stage 9.3.2 baseline measurements, the existing
SMS/latency/cost budgets, and the safety requirement for zero fabricated current-status claims;
the owner and rationale must be recorded. Thresholds must include a non-regression requirement
against the baseline, an allowed latency and cost budget, and a zero-tolerance or explicitly justified ceiling for fabricated claims, invalid
citations, and static answers to current-status questions. If no candidate meets every threshold,
retain the baseline and document the failing dimensions; do not lower thresholds after seeing
results.

## Reproducibility and report format

Store only safe, redacted evaluation artifacts. The report must include:

1. status (`Proposed` until deliberately implemented), objective, date, operator, and decision;
2. corpus SHA-256 and source/version identifier, without account-specific IDs or secrets;
3. embedding model, region, parser/chunking implementation version, top-k, score threshold,
   timeout, prompt version, generation settings, and candidate matrix;
4. pre-registered thresholds, fixture version, and gold-label review record;
5. aggregate and per-case recall/precision, score, latency, cost, citation, grounding, and
   negative/current-status results;
6. failure examples represented by question/evidence IDs and short redacted labels, never raw
   prompts, excerpts, model responses, or provider payloads;
7. baseline comparison, confidence/limitations, and the safe rollout decision.

An independent offline rerun using the recorded inputs must reproduce candidate ordering exactly
for fixture-backed retrieval, within a documented tolerance for measured latency. Live retrieval
ordering is not expected to be stable; report top-k membership and aggregate metrics over repeated
runs instead. If live retrieval is used, retain only aggregate metrics and redacted IDs; never
commit generated AWS configuration or account-specific Knowledge Base/data-source IDs.

## Safe rollout decision

Recommend a candidate for rollout only when it passes all pre-registered retrieval, generation,
negative/current-status, citation, latency, cost, and SMS-bound thresholds; has no unresolved
privacy or prompt-boundary issue; and has a reviewed, redacted report. Roll out one configuration
change at a time, preserve the prior baseline for rollback, and require an explicit deployment and
one-time ingestion authorization in a later implementation stage.

Otherwise recommend retaining the Stage 9.3.2 baseline or rejecting the experiment as
inconclusive. This spec authorizes evaluation design and reporting only; it does not authorize
corpus refresh, ingestion automation, deployment, or live SMS.

## Implementation record — offline capability

Date: 2026-09-05

Implemented `scripts/retrieval_eval.py` and `tests/evals/fixtures/retrieval_golden.json` as a
deterministic lexical retrieval baseline over the checked-in corpus. The runner covers the four
bounded chunking variants, top-k 1/3/5, the reviewed park/rental/negative/current-status cases,
independent deterministic generation/citation scoring, preregistered thresholds, corpus hashing,
and redacted JSON output. `scripts/benchmark_rag_retrieval.py --demo` provides a local query-to-
evidence/source-metadata demonstration. Current-status cases are routed to a labeled live-status
boundary in the evaluation and never invoke retrieval.

This does not establish Bedrock/Titan ranking, provider latency, generation quality, or a rollout
recommendation. The Stage 9.3.2 deployed baseline remains unchanged pending any separately
authorized live retrieval evaluation and later deployment decision.

## Implementation record — live baseline characterization

Date: 2026-09-05

An explicitly authorized, read-only retrieval check ran against the deployed Demo capture stack
using seven synthetic golden questions and `top_k=5`: Algonquin guide information, Killarney
camping, Arrowhead facilities, multi-park canoeing, canoe rentals, unsupported Portage Store
hours/prices, and an unknown park. No Lambda invocation, ingestion mutation, SNS publish, or SMS
send occurred. The check retained only aggregate outcomes and safe metadata labels.

All seven questions returned five results. The results exposed a baseline citation limitation:
park and section metadata were absent, and the source metadata resolved to the generic public
Ontario Parks locator URL. Unsupported and unknown-park questions also returned generic corpus
hits, so retrieval membership alone cannot be treated as answer-bearing evidence. No candidate
configuration was promoted. The safe decision is to retain the deployed baseline while a later,
separately scoped change addresses per-section metadata, negative-query handling, and live
generation/citation evaluation.

## Acceptance criteria

- The golden set includes Algonquin, Killarney, Arrowhead, canoe rentals versus `Rentals - Canoe`,
  unsupported Portage Store facts, a negative park, and current-status cases.
- Retrieval and generation are scored independently, with top-k recall/precision and the required
  score, latency, cost, citation, grounding, and negative/current-status measures.
- The fixed-size and heading-aware chunking variants and top-k matrix are specified and bounded.
- Numeric thresholds are selected and recorded before experiments; no post-hoc threshold change is
  accepted.
- The report format supports a reproducible, redacted comparison and a retain/tune/reject rollout
  decision.
- No corpus refresh, ingestion automation, deployment, hidden provider call, SMS send, or
  unrelated file change is included. Explicit live checks remain opt-in and separately reported.
