from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def command_version(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate every prerequisite before QLoRA training")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "training/preflight-report.json")
    args = parser.parse_args()
    checks = []

    def add(name: str, ok: bool, detail: object) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    version = tuple(int(item) for item in platform.python_version_tuple()[:2])
    add("python_3_11", version >= (3, 11), platform.python_version())
    docker = command_version(["docker", "--version"])
    add("docker_available", bool(docker), docker or "not found")
    git = command_version(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    add("git_sha", bool(git), git or "repository has no commit")

    cuda = bf16 = False
    torch_version = "not installed"
    try:
        import torch

        torch_version = torch.__version__
        cuda = torch.cuda.is_available()
        bf16 = cuda and torch.cuda.is_bf16_supported()
    except ImportError:
        pass
    add("cuda_available", cuda, {"torch": torch_version, "cuda": cuda})
    add("bf16_supported", bf16, bf16)

    free_gb = shutil.disk_usage(ROOT).free / (1024**3)
    add("disk_headroom_40gb", free_gb >= 40, round(free_gb, 2))
    raw = ROOT / "training/datasets/raw"
    counts = {split: line_count(raw / f"{split}.jsonl") for split in ("train", "dev", "blind")}
    add("training_count_2500_4000", 2500 <= counts["train"] <= 4000, counts["train"])
    add("development_count_300", counts["dev"] >= 300, counts["dev"])
    add("blind_count_300", counts["blind"] >= 300, counts["blind"])
    add(
        "safety_count_100",
        line_count(ROOT / "data/evaluation/safety_v1.jsonl") >= 100,
        line_count(ROOT / "data/evaluation/safety_v1.jsonl"),
    )
    add(
        "ambiguity_count_80",
        line_count(ROOT / "data/evaluation/ambiguity_v1.jsonl") >= 80,
        line_count(ROOT / "data/evaluation/ambiguity_v1.jsonl"),
    )
    smoke_path = ROOT / "training/datasets/llamafactory/text2sql_smoke_v1.json"
    smoke_count = len(json.loads(smoke_path.read_text(encoding="utf-8"))) if smoke_path.exists() else 0
    add("smoke_training_count_100", smoke_count == 100, smoke_count)
    add(
        "baseline_predictions_exist",
        any((ROOT / "experiments/reports").glob("E00*.json")),
        "experiments/reports/E00*.json",
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ready": all(check["ok"] for check in checks),
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and not report["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
