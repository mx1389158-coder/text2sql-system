from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a validated adapter and immutable evidence")
    parser.add_argument("model_id")
    parser.add_argument("adapter", type=Path)
    parser.add_argument("metrics", type=Path)
    parser.add_argument("--registry", type=Path, default=Path("training/model_registry.json"))
    parser.add_argument(
        "--split-manifest", type=Path,
        default=Path("training/datasets/llamafactory/split_manifest.json"),
    )
    args = parser.parse_args()
    if not (args.adapter / "adapter_config.json").exists():
        raise FileNotFoundError("adapter_config.json not found")
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    if "execution_accuracy" not in json.dumps(metrics):
        raise ValueError("metrics report does not contain execution_accuracy")
    manifest_hash = hashlib.sha256(args.split_manifest.read_bytes()).hexdigest()
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("a committed Git SHA is required before model registration") from error
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    model = next((item for item in registry["models"] if item["id"] == args.model_id), None)
    if model is None:
        raise ValueError(f"unknown model id: {args.model_id}")
    model.update(
        {
            "adapter": str(args.adapter.as_posix()),
            "status": "validated",
            "metrics": metrics,
            "git_sha": git_sha,
            "data_manifest_sha256": manifest_hash,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    args.registry.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
