# Model card: qwen25-coder-1.5b-text2sql-v1

Status: trained, not validated for release.

## Provenance

- Base model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`.
- Base model SHA-256: `c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8`.
- LLaMA-Factory: `0.9.6.dev0`.
- Config: `training/configs/qwen25_coder_1_5b_qlora.yaml`.
- Config SHA-256: `dc1e23a92374e479662d6f3b46c5cccd7145ede309e95999af935ee6963b412f`.
- Adapter SHA-256: `c8a725fadb6563cf463c7e69b5f0c7a4301b0a1467bfd27042f896896b12362f`.
- Data: 2,500 train / 300 dev / 300 frozen blind examples; all SQL was parsed and
  executed against the dedicated PostgreSQL snapshot before sealing.

## Training

- Hardware: NVIDIA GeForce RTX 5060 Laptop GPU, BF16, PyTorch 2.11.0+cu128.
- Method: NF4 QLoRA, rank 16, alpha 32, 3 epochs, seed 42.
- Runtime: 1,843.76 seconds; 471 optimizer steps.
- Best checkpoint: step 400, dev eval loss 0.07584785.
- Final train loss: 0.03107815.

## Frozen blind evaluation

Both reports use frozen dataset SHA-256
`55c5ab0f7cefbb5a76e7fd7c73492f6a64f111c2e5f574428a361b57a7740eac`.

| Experiment | SQL valid | Execution success | Execution accuracy | p50 latency | Model calls |
| --- | ---: | ---: | ---: | ---: | ---: |
| E10: tuned baseline | 84.00% | 37.33% | 32.00% | 6.84 s | 299 |
| E11: tuned optimized | 98.67% | 85.67% | 19.67% | 12.17 s | 673 |

E11 improved validity and executability but reduced result correctness. Candidate selection favored
executable, semantically wrong SQL; execution repair fixed zero samples. The adapter therefore fails
the release gate and must not be served as a validated model.

## Known limitations and required controls

- Repeated failures use nonexistent columns such as `firmware_versions.model_code` and
  `devices.ended_at`.
- The current candidate scorer does not reliably distinguish executable wrong results.
- The model is sensitive to the runtime prompt and output-token budget.
- The model may only propose SQL. SQLGuard, scoped table permissions, statement timeouts and the
  database read-only role remain mandatory.

