from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    base_path = ROOT / "training/configs/qwen25_coder_1_5b_qlora.yaml"
    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    variants = {
        "lora_rank8": {"lora_rank": 8, "lora_alpha": 16},
        "lora_rank32": {"lora_rank": 32, "lora_alpha": 64},
        "cutoff1024": {"cutoff_len": 1024},
        "cutoff2048": {"cutoff_len": 2048},
    }
    output_dir = ROOT / "training/configs/ablations"
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, overrides in variants.items():
        config = deepcopy(base)
        config.update(overrides)
        config["output_dir"] = f"training/outputs/ablations/{name}"
        (output_dir / f"{name}.yaml").write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
