from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import shutil
import subprocess
import urllib.request
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
    isolated_vm = None
    vbox_manage = Path(r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe")
    if not docker and vbox_manage.exists():
        vm_info = command_version(
            [str(vbox_manage), "showvminfo", "nebula-text2sql-docker", "--machinereadable"]
        )
        if vm_info:
            state = next(
                (
                    line.split("=", 1)[1].strip('"')
                    for line in vm_info.splitlines()
                    if line.startswith("VMState=")
                ),
                "unknown",
            )
            isolated_vm = {"name": "nebula-text2sql-docker", "state": state}
    deployed_health = None
    try:
        with urllib.request.urlopen("http://127.0.0.1:18000/health", timeout=3) as response:
            deployed_health = {"url": response.url, "status": response.status}
    except (OSError, TimeoutError):
        pass
    container_ready = (
        bool(docker)
        or bool(isolated_vm and isolated_vm["state"] == "running")
        or bool(deployed_health and deployed_health["status"] == 200)
    )
    add(
        "container_runtime_available",
        container_ready,
        docker or deployed_health or isolated_vm or "Docker and isolated VirtualBox VM not found",
    )
    git = command_version(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    add("git_sha", bool(git), git or "repository has no commit")

    cuda = bf16 = False
    compute_capability = None
    device_name = None
    bnb_4bit_operator = False
    torch_version = "not installed"
    try:
        import torch

        torch_version = torch.__version__
        cuda = torch.cuda.is_available()
        bf16 = cuda and torch.cuda.is_bf16_supported()
        if cuda:
            device_name = torch.cuda.get_device_name(0)
            compute_capability = list(torch.cuda.get_device_capability(0))
            try:
                import bitsandbytes as bnb

                probe = torch.linspace(-1, 1, 256, device="cuda", dtype=torch.bfloat16)
                quantized, state = bnb.functional.quantize_4bit(probe, quant_type="nf4")
                restored = bnb.functional.dequantize_4bit(quantized, state)
                bnb_4bit_operator = bool(torch.isfinite(restored).all().item())
            except (ImportError, RuntimeError, AttributeError):
                bnb_4bit_operator = False
    except ImportError:
        pass
    add(
        "cuda_available",
        cuda,
        {
            "torch": torch_version,
            "cuda": cuda,
            "device": device_name,
            "compute_capability": compute_capability,
        },
    )
    add("bf16_supported", bf16, bf16)
    add("bitsandbytes_nf4_operator", bnb_4bit_operator, bnb_4bit_operator)

    dependency_versions = {}
    for package in ("torch", "transformers", "peft", "bitsandbytes", "llamafactory"):
        try:
            dependency_versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            dependency_versions[package] = None
    add(
        "dependency_versions_available",
        all(dependency_versions.values()),
        dependency_versions,
    )
    lock_files = [
        "environment.yml",
        "requirements-lock.txt",
        "apps/web/package-lock.json",
        "docker-compose.yml",
    ]
    add(
        "dependency_locks_present",
        all((ROOT / path).is_file() for path in lock_files),
        lock_files,
    )
    train_config = ROOT / "training/configs/qwen25_coder_1_5b_qlora_v5.yaml"
    inference_config = ROOT / "training/configs/inference_tuned_v5.yaml"
    add(
        "training_inference_configs_separated",
        train_config.is_file() and inference_config.is_file(),
        {"training": str(train_config.relative_to(ROOT)), "inference": str(inference_config.relative_to(ROOT))},
    )

    free_gb = shutil.disk_usage(ROOT).free / (1024**3)
    add("disk_headroom_40gb", free_gb >= 40, round(free_gb, 2))
    raw = ROOT / "training/datasets/raw"
    counts = {split: line_count(raw / f"{split}.jsonl") for split in ("train", "dev", "blind")}
    add("training_count_at_least_2500", counts["train"] >= 2500, counts["train"])
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
