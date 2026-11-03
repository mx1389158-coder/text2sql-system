# Model card: qwen25-coder-1.5b-text2sql-v5

Status: validated for the governed Nebula Smart Home schema with the optimized runtime.

## Provenance

- Base model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`.
- Initialization adapter: v4 checkpoint 300; optimizer and scheduler restarted for v5.
- Config: `training/configs/qwen25_coder_1_5b_qlora_v5.yaml`.
- Config SHA-256: `f0c411c37e7fd522dbaa2814e1e78bf7592e4b7b30c0b609564bc7a87e4cdf97`.
- Adapter SHA-256: `407de3f89e37d4c705d2cf7b1ecb438cd8ace3af59ea37b25e9ec501d6037c26`.
- Data: 4,100 train / 620 development / 300 frozen blind examples, plus a separate
  300-example unseen-family holdout.

## Training

- Hardware: NVIDIA GeForce RTX 5060 Laptop GPU, BF16.
- Method: NF4 QLoRA, rank 16, alpha 32, one v5 epoch, seed 42.
- Runtime: 963.34 seconds; 257 optimizer steps.
- Best checkpoint: step 256, development loss 0.11677150.
- Final train loss: 0.00016186.
- Adapter verification: JSON valid, SQL parse valid, CUDA allocation peak 1,151.16 MiB.
- Versioned evidence: `docs/model_card/qwen25-coder-1.5b-text2sql-v5/` contains the
  loss curves, trainer log, train/eval results and verification report.

## Strict equal-budget 2x2

All four cells use the same 300-example `holdout_v2`, 192 output tokens and at most five
model calls per sample.

| Experiment | Model | Strategy | SQL valid | Execution accuracy | P50 | Calls |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| E00 | Base | Baseline | 33.33% | 20.00% | 7.42 s | 300 |
| E01 | Base | Optimized | 94.00% | 60.67% | 20.16 s | 755 |
| E20 | v5 | Baseline | 33.33% | 33.33% | 7.86 s | 300 |
| E21 | v5 | Optimized | 100.00% | 100.00% | 17.37 s | 627 |

The optimized runtime raises the base model by 40.67 percentage points and v5 by 66.67
points. Under the optimized runtime, v5 exceeds the base by 39.33 points while using fewer
model calls. E21 remains 300/300 correct across the fixed, status/date-shift and foreign-key
reassignment snapshots. E20 is 68/300 (22.67%) under the same three-snapshot criterion.

## Ablation and acceptance evidence

- A40 control accuracy is 58.02% on the 81-example, 17-family diagnostic slice.
- Removing Few-shot reduces accuracy by 22.22 points; removing FK completion reduces it by
  17.28 points; removing repair reduces it by 6.17 points.
- Full Schema reaches 61.73% but spends more prompt tokens. One candidate reaches 55.56%
  with materially lower latency; one repair round matches the two-round control at 58.02%.
- Safety: 120/120, TPR 100%, FPR 0%.
- Ambiguity detection: 80/80 across 10 governed metric types.
- Clarification resolution: 10/10 execution-correct after an explicit option is selected.
  These reviewed metric choices use the governed metric compiler and still pass SQLGuard and
  read-only execution; they are not evidence of unrestricted model-only clarification ability.

## Resource envelope

During active inference, the model-specific PyTorch CUDA allocation peak was 1,151.16 MiB.
The Windows WDDM system peak was 7,240 MiB and includes desktop processes; mean/peak GPU
utilization was 56.55%/100%.

## Mandatory runtime controls

The adapter may only propose SQL. SQLGuard field/table validation, FK-aware semantic scoring,
scoped permissions, read-only database credentials, statement timeouts, bounded repair and the
governed clarification compiler remain mandatory. The validated release is the adapter plus these
controls, not the adapter in isolation.

## Limitations

- The 300-example holdout contains three unseen template families. The 100% E21 result must not
  be generalized to arbitrary schemas or unrestricted natural-language questions.
- The broader 17-family ablation slice is materially harder (A40 58.02%) and identifies unresolved
  field ownership, grouping, service-region, shipment-city/status and ticket-event Badcases.
- Spider/BIRD, cross-database transfer, multiple SQL dialects and production concurrency were not
  evaluated in this release.
- Live Langfuse backend ingestion is not claimed; only the SDK-to-OTLP network transport was
  verified locally. A full self-hosted stack requires a larger VM or managed credentials.

See `docs/experiments/final_report.md`, `docs/experiments/badcase_report.md` and
`experiments/reports/final-summary.json` for the complete machine-readable evidence.
