# Project status

Last verified: 2026-11-03 (Asia/Shanghai).

| Phase | Status | Verified evidence |
| --- | --- | --- |
| P0 environment/database | Complete | Dedicated `nebula-text2sql-docker` VM; 23-table PostgreSQL; 50,003 orders, 30,002 devices and 20,003 tickets; read-only writes denied; backup/restore drill passed |
| P1 base Text2SQL | Complete | Structured generation, AST/schema guard, scoped permissions, persistence, SSE, security rejection and real local model endpoint verified |
| P2 Schema Linking | Complete | Hybrid retrieval, adaptive expansion, FK completion, compact M-Schema, Few-shot retrieval, clarification and caches covered by tests and ablations |
| P3 data/QLoRA | Complete | Governed 4,100/620/300 splits, separate 300-example holdout, v5 QLoRA and immutable training/model-card evidence |
| P4 strategy | Complete | Candidate semantic scoring, batched generation, execution-grounded selection, bounded repair and governed clarification compiler implemented and measured |
| P5 evaluation/full stack | Complete | Strict 2x2, nine ablations, three-snapshot Test-Suite, safety/ambiguity, resource measurement, browser QA and final reports complete |

## v2 chapter revision

The 15-chapter revision is implemented in `docs/PROJECT_PLAN_V2.md`. New verified evidence includes
CUDA/BF16/NF4 operator preflight, dry-run checkpoint recovery, zero-leak split stratification,
32-FK snapshot validation, role-level column/sample-value filtering, Prompt version tracing, explicit
result-equivalence rules, four product scenarios (4/4), and the canonical E00/E01/E10/E11 role map.
No model training or frozen experiment was rerun for this documentation and reliability revision.

## Release result

- Strict equal-budget 2x2 on the same 300-example holdout and 192-token budget:
  E00 20.00%, E01 60.67%, E20 33.33%, E21 100.00% execution accuracy.
- E21 remains 300/300 correct across fixed, status/date-shift and FK-reassignment snapshots.
- A40–A48 are complete. A40 is 58.02% on the broader 81-example, 17-family slice;
  removing Few-shot costs 22.22 points and removing FK completion costs 17.28 points.
- Safety is 120/120 (TPR 100%, FPR 0%); ambiguity detection is 80/80; reviewed
  clarification resolution is 10/10 execution-correct.
- Browser acceptance is 8/8; dedicated VM backup/restore passed; v5 model-specific CUDA
  allocation peak is 1,151.16 MiB.
- Langfuse Cloud Japan authentication, ingestion and API readback passed; a real Text2SQL request
  produced five readable stage observations without storing credentials in Git or evidence files.
- Long evaluations now checkpoint every completed sample and reuse matching completed reports.
  `--no-resume` is required to force a deliberate rerun.

## Release boundary

The validated unit is v5 plus the optimized governed runtime and SQL safety controls. The 300-example
holdout covers three unseen template families, so the 100% E21 result is not a claim of arbitrary-schema
or cross-database generalization. The 17-family Badcase report remains the source for the next iteration.

## Observability deployment

Live Langfuse Cloud ingestion is complete. The dedicated `nebula-text2sql-docker` API uses managed
Langfuse credentials supplied through its ignored `.env`; authentication, direct ingestion and
readback of all five stages from a real Text2SQL request passed. Self-hosting is no longer required for
this release. The redacted machine-readable evidence is `docs/qa/langfuse_cloud_report.json`.

See `docs/experiments/final_report.md`, `docs/experiments/badcase_report.md` and
`docs/qa/acceptance_checklist.md`.
