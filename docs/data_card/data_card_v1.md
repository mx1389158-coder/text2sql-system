# 星云智家 Text2SQL data card v1

## Current state

The governed local corpus contains 2,500 training, 300 development and 300 blind examples. It also
contains 100 safety cases, 80 ambiguity cases and a separate 100-example overfit smoke set. Three
train, one development and one blind example are manually authored; the remainder come from
versioned business templates whose questions and SQL are generated together and execution-checked.

Current hashes were generated against `data/snapshots/demo.db`. They prove pipeline consistency, not
production model quality. Before formal evaluation, rebuild the target-scale PostgreSQL snapshot,
rerun `build_governed_corpus.py`, prepare the dataset and reseal development/blind sets.

## Dataset gates

- train: 2,500 examples grouped by semantic template;
- development: 300 examples used for model and strategy selection;
- frozen blind: 300 SQL-free evaluation examples with result hashes;
- safety: 100 normal/read-write/injection/permission cases;
- ambiguity: 80 questions where clarification is expected.

Splits are disjoint by `template_group` and normalized question. Every gold SQL must execute on the
same versioned snapshot. Equivalent SQL is evaluated by results rather than text alone. Empty
results are reviewed instead of automatically treated as wrong.

## Governance

Feedback is stored as a candidate Badcase and never enters training automatically. A reviewer must
validate the question, SQL, business definition and snapshot before promoting a revision. Raw blind
Gold SQL is git-ignored; formal manifests reference SQL-free sealed files and fixed SHA-256 values.
Each preparation run stores split hashes, per-example result hashes and row counts.

