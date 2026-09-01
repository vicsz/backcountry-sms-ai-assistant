# Bug register

This register tracks defects in the assistant and its development artifacts. Each entry links to
one detailed Markdown record in this directory.

Statuses are `Open`, `Investigating`, `Fixed Locally`, `Awaiting Live Verification`, and `Closed`.
`Closed` requires passing automated validation and any live verification required by the defect.

| ID | Title | Status | Cause | Fix | Tests | Commit | Live verification |
| --- | --- | --- | --- | --- | --- | --- | --- |

| BUG-0001 | Collingwood weather request was rejected | Closed | Nova Micro omitted the redundant current-location field; strict validation rejected the grounded place | Canonicalized the grounded current place, clarified prompt, and strengthened Ontario ranking | Collingwood path, omitted-field, prompt, and Ontario preference regressions | [d951ff1](https://github.com/vicsz/backcountry-sms-ai-assistant/commit/d951ff1) | Demo capture passed; only deployed target |
