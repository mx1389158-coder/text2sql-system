from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import yaml


REQUIRED_STATE = ("trainer_state.json", "optimizer.pt", "scheduler.pt")


def latest_checkpoint(output_dir: Path) -> Path:
    checkpoints = []
    for path in output_dir.glob("checkpoint-*"):
        if not path.is_dir():
            continue
        try:
            step = int(path.name.removeprefix("checkpoint-"))
        except ValueError:
            continue
        checkpoints.append((step, path))
    if not checkpoints:
        raise FileNotFoundError(f"no checkpoint-* directory found in {output_dir}")
    return max(checkpoints, key=lambda item: item[0])[1]


def validate_checkpoint(path: Path) -> None:
    missing = [name for name in REQUIRED_STATE if not (path / name).is_file()]
    if missing:
        raise ValueError(f"checkpoint is not resumable; missing: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely resume QLoRA from the latest complete checkpoint"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("training/configs/qwen25_coder_1_5b_qlora_v5.yaml"),
    )
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("training/resume-plan.json")
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output_dir = Path(config["output_dir"])
    checkpoint = args.checkpoint or latest_checkpoint(output_dir)
    validate_checkpoint(checkpoint)
    executable = shutil.which("llamafactory-cli") or str(
        Path(".conda/Scripts/llamafactory-cli.exe")
    )
    command = [
        executable,
        "train",
        str(args.config),
        "--resume_from_checkpoint",
        str(checkpoint),
    ]
    report = {
        "config": str(args.config),
        "output_dir": str(output_dir),
        "checkpoint": str(checkpoint),
        "checkpoint_state_complete": True,
        "execute": args.execute,
        "command": command,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.execute:
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
