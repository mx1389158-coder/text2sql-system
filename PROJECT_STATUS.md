# Project status

Last verified: 2026-10-28 (Asia/Shanghai).

| Phase | Implemented | Verified here | Remaining environment run |
| --- | --- | --- | --- |
| P0 environment/database | Project-local Python 3.11 environment, isolated-port Compose stack, dedicated VirtualBox VM, 23-table PostgreSQL migration, read-only role, exact-scale deterministic generator, SQLite demo snapshot | Ubuntu 24.04 VM deployed; API/Web/PostgreSQL healthy; 23 tables and target scale verified; read-only writes denied | Production backup/restore drill and external TLS/domain configuration |
| P1 base Text2SQL | Structured prompt, retrying demo/OpenAI-compatible providers, AST/schema/table guard, scoped permissions, rate/concurrency limits, persistent queries, live SSE | API E2E, persistence and 100-case security tests | Run with the selected real local model endpoint |
| P2 Schema Linking | Versioned catalog, hybrid lexical/dense retrieval, low-confidence expansion, FK completion, compact M-Schema, Few-shot retrieval, clarification and three caches | Unit/E2E tests and full labeled split preparation | Tune thresholds on real-model development predictions |
| P3 data/QLoRA | 2,500/300/300 governed splits, 100 safety, 80 ambiguity, 100 training smoke, SQL execution/result hashes, leakage gates, QLoRA and ablation configs, preflight and registry tooling | PostgreSQL-backed hashes regenerated; CUDA/BF16/NF4 verified; 100-example real QLoRA smoke and exact overfit inference passed | Run full QLoRA, frozen-blind evaluation, then register the adapter |
| P4 strategy | 1/3 candidates, lightweight semantic scoring, execution-grounded selection, timeout-aware repair, result/schema/Few-shot caches, persistent trace and Langfuse v5 sink | Pipeline tests and equal-budget manifests | Run E01/E10/E11 with real base/tuned models and a live Langfuse deployment |
| P5 evaluation/full stack | Full metric schema, frozen hash-only sets, 2x2 + 8 system + 4 training ablations, durable eval jobs, Vue query/schema graph/experiments/Badcase/chart pages | 34 tests, Ruff, Vue production build, Docker health checks, PostgreSQL-backed frozen sets, 300-case demo E00 baseline | Run real-model matrix/ablations and manual browser QA |

The existing demo reports demonstrate plumbing only. The 300-case E00 run uses deterministic demo
rules and records zero execution accuracy on the frozen set; it is not a model-quality result. The
registry keeps the adapter in `not_trained` status until a full GPU run and frozen-blind evaluation
exist. Automatically generated business templates and their result hashes have now been regenerated
and execution-verified against the dedicated PostgreSQL snapshot.

