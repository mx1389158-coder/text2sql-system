from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def sample_gpu() -> dict[str, float | str]:
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()
    name, total, used, utilization, power = [item.strip() for item in output.split(",")]
    return {
        "gpu": name,
        "memory_total_mb": float(total),
        "memory_used_mb": float(used),
        "utilization_percent": float(utilization),
        "power_watts": float(power),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample end-to-end GPU resources during inference")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--experiment", type=Path, default=Path("experiments/reports/E21.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/reports/inference-resources-v5.json"),
    )
    parser.add_argument("--torch-allocated-peak-mb", type=float, default=1151.16)
    parser.add_argument(
        "--workload",
        default="qwen25-coder-1.5b-text2sql-v5 OpenAI-compatible inference",
    )
    args = parser.parse_args()

    samples = []
    started = time.perf_counter()
    while time.perf_counter() - started < args.duration:
        samples.append({"elapsed_seconds": time.perf_counter() - started, **sample_gpu()})
        time.sleep(max(0.05, args.interval))
    experiment = json.loads(args.experiment.read_text(encoding="utf-8"))
    used = [float(row["memory_used_mb"]) for row in samples]
    utilization = [float(row["utilization_percent"]) for row in samples]
    power = [float(row["power_watts"]) for row in samples]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workload": args.workload,
        "measurement": {
            "source": "nvidia-smi sampled at the host GPU during active inference",
            "duration_seconds": time.perf_counter() - started,
            "interval_seconds": args.interval,
            "sample_count": len(samples),
            "gpu": samples[0]["gpu"],
            "gpu_memory_total_mb": samples[0]["memory_total_mb"],
            "system_gpu_memory_min_mb": min(used),
            "system_gpu_memory_peak_mb": max(used),
            "system_gpu_memory_observed_delta_mb": max(used) - min(used),
            "gpu_utilization_mean_percent": statistics.fmean(utilization),
            "gpu_utilization_peak_percent": max(utilization),
            "power_mean_watts": statistics.fmean(power),
            "power_peak_watts": max(power),
            "torch_model_cuda_allocated_peak_mb": args.torch_allocated_peak_mb,
            "caveat": (
                "Windows WDDM does not expose per-process VRAM through nvidia-smi; system memory "
                "includes desktop applications. The PyTorch allocation peak is the model-specific "
                "measurement and system peak is the end-to-end upper bound."
            ),
        },
        "experiment_reference": {
            "id": experiment["experiment"]["id"],
            "model": experiment["experiment"]["model"],
            "p50_latency_ms": experiment["summary"]["p50_latency_ms"],
            "p95_latency_ms": experiment["summary"]["p95_latency_ms"],
            "model_calls": experiment["summary"]["model_calls"],
            "prompt_tokens": experiment["summary"]["prompt_tokens"],
            "completion_tokens": experiment["summary"]["completion_tokens"],
        },
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**report["measurement"], **report["experiment_reference"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
