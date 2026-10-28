# ADR 0001: Modular Text2SQL pipeline

Status: accepted.

The system separates schema retrieval, generation, static safety, database execution and
evaluation. A model provider can be replaced without changing the database boundary. The static
guard can reject model output deterministically, and the PostgreSQL account remains read-only even
if the guard has a defect.

Reference projects informed, but were not copied into, this implementation:

- XiYan-SQL informed the structured table/column/example/foreign-key presentation. This project
  uses its own immutable catalog and retrieval evidence types.
- SQLGlot is used as a dependency for PostgreSQL AST parsing and rewriting; access control is local.
- LLaMA-Factory supplies the training runtime. Our dataset conversion and experiment manifests are
  project-owned.
- Harness² informed the separation between task adapters, runs and scoring. We keep frozen datasets
  and reports separate from predictions.
- Langfuse is an optional tracing backend; correctness never depends on it.

