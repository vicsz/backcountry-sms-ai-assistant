# Enhancement register

This register tracks bounded capability improvements that are selected for implementation. Early
ideas that are not yet scoped remain in [`docs/ideas.md`](../docs/ideas.md).

| ID | Title | Status | Acceptance tests | Commit |
| --- | --- | --- | --- | --- |
| ENH-0001 | Current-news capability response | Closed | `test_enh_0001_current_news_explains_data_boundary_without_model_or_retrieval`; demo capture passed | `b59091f` |
| ENH-0002 | Operational dashboard clarity and recent-error visibility | Closed | `test_dashboard_is_single_demo_dashboard_for_every_stack`; `test_dashboard_prioritizes_demo_health_calls_and_recent_redacted_events`; demo inspection `ENH-0002-DASHBOARD-001` | `e1815d3`, `e51e1c4` |
| ENH-0003 | Rust default, test ownership, and documentation cleanup | Closed | Rust default/rollback stack tests; Rust package/CI gates; RAG and deployment-boundary wording | `23766a2` |
| ENH-0004 | RAG quality gates and park-scoped retrieval | Partially implemented | Python/Rust park scoping and time-sensitive routing; offline retrieval evaluator | Current worktree |
| ENH-0005 | Fire-ban ingestion normalization and local promotion primitive | Partially implemented | Provenance, deterministic snapshot, validation failure, atomic pointer tests | Current worktree |
| ENH-0006 | Python runtime boundary cleanup | Closed; rollback/oracle boundary superseded by ENH-0007 | Rust-only deployed target; ownership documentation | `aa10752` superseded the remaining boundary |
| ENH-0007 | Rust runtime test parity and Python oracle retirement | Implemented; deployed and verified | Rust failure-path contracts; no Python request/capture Lambda; no Python oracle CI gate | `aa10752` |
| ENH-0008 | Retire the legacy Python context table safely | Implemented; detached; data disposed by ENH-0009 | Retain policy, safe CDK detach, no data deletion | `e46764e`, `94d6870` |
| ENH-0009 | Dispose of retained legacy context data | Implemented; deletion verified | Metadata-only review, exact-table deletion, post-delete verification | `87dcb5f`, `500428e` |
| ENH-0010 | Public repository release hygiene | Implemented locally; publication decision separate | Truthful status, privacy scan, generated-file hygiene, public documentation review | `1a68ed8` |
