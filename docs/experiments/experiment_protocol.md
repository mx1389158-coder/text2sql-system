# Experiment protocol

The E00/E10/E01/E11 manifests isolate model adaptation from execution strategy. Every comparison
uses the same frozen database, dataset hash, maximum model calls and maximum output tokens.

Required report fields are SQL Valid Rate, Execution Accuracy, Schema Recall@k, clarification
accuracy, safety TPR/FPR, repair gain, p50/p95 latency, call count, peak VRAM and wall time. Failed or
unscored samples remain visible and are never silently converted to zero or dropped.

Ablations cover examples, foreign-key completion, full versus adaptive schema, one versus three
candidates, 0/1/2 repair rounds, LoRA rank 8/16/32 and cutoff 1024/1536/2048. Development data chooses
the configuration; only the chosen system is evaluated on the frozen blind set.

