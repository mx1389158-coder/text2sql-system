# 星云智家 Text2SQL data card v1

## Current state

The governed local corpus contains 4,100 training, 620 development and 300 frozen blind examples.
It also contains a separate 300-example holdout, 100 SQL safety cases, 20 request safety cases,
80 ambiguity cases, 10 result-hashed clarification-resolution cases and a
100-example overfit smoke set. Manually authored seed cases and versioned business templates are
generated with their SQL and execution-checked together. The v3 increment contains 900 reviewed
correction examples and 180 disjoint development examples covering wrong field ownership, invented
columns, wrong fact tables, missing bridge tables and invalid join keys. Rejected SQL is retained as
audit metadata; SFT consumes only the reviewed correction. The v4/v5 increment adds complete table
coverage and focused examples for shipments, customer addresses, regions, payments, fault codes,
ticket events and warehouses while keeping the three holdout business families SQL-free.

Formal development, blind, holdout and clarification-resolution hashes were generated against the
dedicated target-scale PostgreSQL snapshot. The small `data/snapshots/demo.db` database remains only
for offline engineering smoke tests and is not the source of published model-quality numbers.

## Dataset gates

- train: 4,100 examples grouped by semantic template, including 900 corrected Badcases and 700
  coverage/bridge examples;
- development: 620 examples used for model and strategy selection;
- frozen blind: 300 SQL-free evaluation examples with result hashes;
- unseen-family holdout: 300 SQL-free examples for delivered shipments, approved refunds and failed
  device upgrades;
- safety: 100 normal/read-write/injection/permission cases;
- ambiguity: 80 questions across 10 business definitions where clarification is expected;
- clarification resolution: 10 reviewed questions with a governed answer and frozen result hash;
- request safety: 20 normal/adversarial questions for prompt-injection and write-request rejection.

Splits are disjoint by `template_group` and normalized question. Every gold SQL must execute on the
same versioned snapshot. Equivalent SQL is evaluated by results rather than text alone. Empty
results are reviewed instead of automatically treated as wrong.

## Governance

Feedback is stored as a candidate Badcase and never enters training automatically. A reviewer must
validate the question, SQL, business definition and snapshot before promoting a revision. Raw blind
and holdout Gold SQL is git-ignored; formal manifests reference SQL-free sealed files and fixed
SHA-256 values.
Each preparation run stores split hashes, per-example result hashes and row counts.

## v2 governance verification

- `dataset_governance_report.json` verifies zero cross-split ID, normalized-question or
  `template_group` leakage and records difficulty, semantic-template and table-combination strata.
- `snapshot_validation_report.json` verifies 23 tables, target-scale counts, all 32 foreign keys,
  read-only write denial, statement timeout, post-timeout connection recovery and valid empty results.
- Business definitions are versioned in `semantic_catalog_v1.json`; the human-readable contract is
  `business_metrics_v1.md`.

