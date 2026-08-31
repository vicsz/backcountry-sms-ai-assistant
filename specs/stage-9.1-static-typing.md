# Stage 9.1 — Static typing and build-time checks

Status: Implemented locally; CI gate and negative check added

## Objective

Introduce static typing with `mypy` so incorrect type contracts fail the build/CI before runtime.
This is a developer and CI quality gate; it does not add runtime validation or change SMS behavior.

## Contract

- Configure `mypy` through the project’s existing dependency and CI conventions.
- Staged adoption is allowed, including a narrow initial module set and incremental strictness, but
  the adopted scope must be explicit.
- New or materially changed typed code must not introduce unreviewed `Any`, ignored errors, or
  unchecked third-party boundaries. Temporary exceptions must be narrow, documented, and tracked.
- A deliberately wrong-type fixture or equivalent negative check must prove that the build fails.
- The final gate is required, not advisory: CI runs the exact documented `mypy` command (or wrapper)
  and it exits successfully for the adopted scope; a type error makes the build fail.
- Runtime input handling, schema validation, coercion, and user-facing error behavior are out of
  scope. Static typing does not replace runtime safeguards.

## Initial adoption

The initial checked scope is the `backcountry_sms` package under Python 3.12 assumptions. The
documented command is `mypy`, configured in `pyproject.toml`; third-party AWS modules remain
explicit adapter boundaries while their stubs are evaluated separately. The CI gate also runs
`scripts/check-mypy-negative.sh`, which proves a deliberately incompatible assignment causes
`mypy` to fail without making the failing fixture part of the normal import or test path.

## Acceptance criteria

1. Configuration, supported Python assumptions, and checked scope are documented.
2. The normal build/CI path runs the type check and fails on a type error.
3. The negative check is not hidden in a live call or deployment hook.
4. Any staged-adoption backlog and exit condition are explicit.

## Non-goals and controls

No application behavior, runtime validation, deployment, live provider call, or SMS send is part of
this stage. Do not commit credentials, generated AWS configuration, or generated type artifacts.
