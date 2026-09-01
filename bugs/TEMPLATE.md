# BUG-#### — Short title

## Status

Open

## Reported behavior

Describe what happened. Preserve the original wording where useful; do not silently correct the
source report.

## Expected behavior

Describe the behavior that should have occurred.

## Reproduction and evidence

- Reproduction input or command:
- Reproduction result:
- Evidence location:

Keep private screenshots, raw SMS, transcripts, phone numbers, coordinates, provider payloads, and
other sensitive material out of the committed record. Store permitted private evidence under an
ignored local path and describe it here without exposing its contents.

## Impact

Describe who or what is affected and the severity or scope.

## Analysis and root cause

Record the analysis, relevant code boundary, and confidence. Separate observed facts from
hypotheses until the cause is confirmed.

## Fix

Describe the smallest implemented change and any explicit non-goals.

## Regression tests

List automated tests added or updated, including the behavior they protect. Every regression test
must link to this bug ID through its test name (for example, `test_bug_0001_<behavior>`) or a
`Regression: BUG-####` docstring/comment. Use exact references:

- `tests/test_file.py::test_bug_####_<behavior>` — behavior protected

Optional model/provider eval cases should use a related case ID such as
`BUG-####-SHORT-NAME-001` and be listed separately from deterministic unit tests.

## Validation results

Record focused checks and the final validation gate, with dates or commands where useful.

## Deployment/live-verification status

State whether deployment or live verification is required. Record evidence separately from local
test results. Identify the target environment, stack/deployment identifier, delivery mode, external
calls, and result. Use `Awaiting Live Verification` only when the applicable deployed target has
not yet been verified; do not assume that target is production.

## Fixing commit

Record the commit hash and message after the change is committed.
