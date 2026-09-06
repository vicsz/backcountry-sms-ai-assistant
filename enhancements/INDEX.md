# Enhancement register

This register tracks bounded capability improvements that are selected for implementation. Early
ideas that are not yet scoped remain in [`docs/ideas.md`](../docs/ideas.md).

| ID | Title | Status | Acceptance tests | Commit |
| --- | --- | --- | --- | --- |
| ENH-0001 | Current-news capability response | Closed | `test_enh_0001_current_news_explains_data_boundary_without_model_or_retrieval`; demo capture passed | Pending |
| ENH-0002 | Operational dashboard clarity and recent-error visibility | Closed | `test_dashboard_is_single_demo_dashboard_for_every_stack`; `test_dashboard_prioritizes_demo_health_calls_and_recent_redacted_events`; demo inspection `ENH-0002-DASHBOARD-001` | `e51e1c4` |
| ENH-0003 | Rust default, test ownership, and documentation cleanup | Closed | Rust default/rollback stack tests; Rust package/CI gates; RAG and deployment-boundary wording | Current commit |
| ENH-0004 | RAG quality gates and park-scoped retrieval | Partially implemented | Python/Rust park scoping and time-sensitive routing; offline retrieval evaluator | Current worktree |
| ENH-0005 | Fire-ban ingestion normalization and local promotion primitive | Partially implemented | Provenance, deterministic snapshot, validation failure, atomic pointer tests | Current worktree |
| ENH-0006 | Python runtime boundary cleanup | Closed; rollback/oracle boundary superseded by ENH-0007 | Rust-only deployed target; ownership documentation | Current worktree |
| ENH-0007 | Rust runtime test parity and Python oracle retirement | Implemented locally; final validation pending | Rust failure-path contracts; no Python request/capture Lambda; no Python oracle CI gate | Current worktree |
| ENH-0008 | Retire the legacy Python context table safely | Implemented; physical data retained | Retain policy, safe CDK detach, no data deletion | Current worktree |
| ENH-0009 | Dispose of retained legacy context data | Implemented; deletion verified | Metadata-only review, exact-table deletion, post-delete verification | Current worktree |
