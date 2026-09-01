# Backcountry SMS AI Assistant

## Repository purpose

This is a Python and AWS CDK project for a bounded, SMS-first backcountry assistant. Work should
be organized around one clearly scoped change at a time, with explicit acceptance criteria and
non-goals.

The repository is also an example of AI-assisted application engineering. Preserve the distinction
between implemented behavior, measured evidence, local experiments, proposed work, and private
publication planning.

## Safety and privacy

- Never commit credentials, tokens, phone numbers, account IDs, secrets, private URLs, raw SMS,
  personal coordinates, production transcripts, or generated account-specific AWS configuration.
- Use the approved SSO profile for normal AWS work. Never copy credentials into the repository.
- Keep real provider calls, deployments, and SMS sends explicit and visible; never hide them in
  tests, hooks, CI, or convenience commands.
- Use synthetic fixtures and public test inputs whenever possible.
- Do not log or expose message bodies, prompts, model responses, raw provider payloads, or other
  sensitive data.

## Scope and stage discipline

- Select one existing spec or explicitly scoped documentation task before making changes.
- Keep implementation within the selected scope. Record future ideas separately rather than
  expanding the current change.
- Keep prospective ideas in [`docs/ideas.md`](docs/ideas.md); they are backlog candidates, not
  committed implementation scope.
- Keep measured performance baselines, experiments, and retrieval benchmarks in
  [`docs/performance.md`](docs/performance.md).
- Do not treat a local implementation, offline test, or proposed architecture as deployed or
  live-verified.
- Preserve authoritative deterministic data boundaries. Do not allow an LLM to invent current
  weather, fire-ban status, closures, coordinates, provider results, or other operational facts.
- Keep SMS length, bounded context, retry limits, privacy, and safe fallback behavior explicit.

## Development workflow

Follow [`development-workflow.md`](development-workflow.md) for implementation, review,
validation, live checks, and commit sequencing.

- Bug, regression, broken-behavior, or failing-behavior work must follow
  [`bug-fixing-workflow.md`](bug-fixing-workflow.md), create or update a record under `bugs/`, and
  add automated regression coverage before commit. Its commit message must begin with the bug ID,
  for example `BUG-0001 -- fix Collingwood weather interpretation`.
- Spec implementation commits must begin with the selected spec identifier, for example
  `SPEC-4.1 -- improve location extraction`.
- The project-local [`bug-fixing-workflow` skill](.codex/skills/bug-fixing-workflow/SKILL.md) may
  guide automatic routing, but this repository instruction and the workflow document remain the
  enforcement authority.

- During iteration, run targeted checks appropriate to the change.
- After review and the final focused fix, run the applicable final validation gate once.
- Documentation-only work requires final diff inspection and `git diff --check` plus independent
  documentation review.
- Code, test, infrastructure, dependency, or runtime-configuration changes require the documented
  Ruff, full pytest, and CDK synthesis gate.
- Provider, Bedrock, Lambda, SNS, or SMS behavior changes require the smallest relevant explicit
  live check after review.
- Update `STATUS.md` when the current work changes project state, but verify its claims against the
  actual diff, deployment state, and evidence. Stale status text is not proof.

## Agent roles

- Use one implementer and one independent reviewer by default.
- The implementer may edit within the owned scope but must not deploy, send SMS, or commit.
- The reviewer is read-only and checks scope, acceptance criteria, regressions, privacy, security,
  generated files, and publication safety.
- Only the parent/orchestrator commits.
- Keep prompts, file scope, context, and reports concise. Do not duplicate parallel work on the
  same change.
- Use the stable role labels `Backcountry Implementer` and `Backcountry Reviewer` in delegated
  prompts and require the same label in the final report.
- Choose the smallest capable model for routine work; reserve a stronger model for materially
  complex CDK/IAM, security, architecture, data-retention, or debugging work.

## Live and test boundaries

- Ordinary unit tests and CI must not make live Bedrock/provider calls or send SMS.
- Live evaluation and SMS checks are opt-in, manually visible actions.
- Prefer direct deployed-handler invocations with the dedicated carrier-independent capture mode
  for provider execution and end-to-end sanity checks.
- A real SMS test requires explicit user authorization and must remain separate from normal tests.
- Test-only capture configuration must fail closed and must not be possible to enable accidentally
  on the production target.

## Public-release hygiene

- Treat the public README, diagrams, examples, and repository history as publication artifacts.
- Review all public material for secrets, personal data, private operational details, misleading
  status claims, and unsupported product or pricing claims.
- Use solid/dashed or equivalent visual labels to distinguish deployed behavior from local or
  proposed architecture.
- Keep private brainstorming and publication-cleanup notes under ignored `local/` paths.
