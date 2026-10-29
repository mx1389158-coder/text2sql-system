# Project status

Last verified: 2026-10-28 (Asia/Shanghai).

| Phase | Implemented | Verified here | Remaining environment run |
| --- | --- | --- | --- |
| P0 environment/database | Project-local Python 3.11 environment, isolated-port Compose stack, dedicated VirtualBox VM, 23-table PostgreSQL migration, read-only role, exact-scale deterministic generator, SQLite demo snapshot | Ubuntu 24.04 VM deployed; API/Web/PostgreSQL healthy; 23 tables and target scale verified; read-only writes denied | Production backup/restore drill and external TLS/domain configuration |
| P1 base Text2SQL | Structured prompt, retrying demo/OpenAI-compatible providers, AST/schema/table guard, scoped permissions, rate/concurrency limits, persistent queries, live SSE | API E2E, persistence and 100-case security tests | Run with the selected real local model endpoint |
| P2 Schema Linking | Versioned catalog, hybrid lexical/dense retrieval, low-confidence expansion, FK completion, compact M-Schema, Few-shot retrieval, clarification and three caches | Unit/E2E tests and full labeled split preparation | Tune thresholds on real-model development predictions |
| P3 data/QLoRA | 2,500/300/300 governed splits, 100 safety, 80 ambiguity, SQL execution/result hashes, leakage gates, QLoRA and registry tooling | Full 3-epoch QLoRA completed in 1,843.76 s; best dev loss 0.07584785; adapter hash and inference verification recorded | Improve model/data and pass the frozen registration gate; current adapter is trained but unvalidated |
| P4 strategy | Batched 3-candidate generation, execution-grounded selection, timeout-aware repair, caches, persistent trace and Langfuse v5 sink | Real E11 completed: 98.67% SQL valid and 85.67% executable, but only 19.67% result accuracy and zero repair gain | Replace/tune semantic candidate scoring; validate repair on targeted badcases; deploy live Langfuse |
| P5 evaluation/full stack | Full metric schema, frozen hash-only sets, 2x2 + ablation manifests, durable eval jobs, Vue query/schema graph/experiments/Badcase/chart pages | 35 tests, Ruff, Vue build, Docker/PostgreSQL health; real E00/E01 diagnostics and frozen E10/E11 reports | Re-run base E00/E01 at the same 192-token budget for strict 2x2 comparability; run ablations and manual browser QA |

The adapter is trained but failed its release gate. E10 reached 32.00% frozen execution accuracy;
E11 regressed to 19.67% despite much higher executability, exposing a candidate-selection quality
problem. E00/E01 were run as 112-token diagnostics and are not strictly comparable with the
192-token tuned runs. Automatically generated templates and result hashes remain execution-verified
against the dedicated PostgreSQL snapshot.

