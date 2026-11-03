from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "experiments/reports"


def load_json(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.2f}%"


def metric(report: dict[str, Any] | None, key: str) -> Any:
    return report.get("summary", {}).get(key) if report else None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def failure_bucket(error: str | None, status: str | None) -> str:
    value = (error or "").lower()
    if "字段不存在" in value or "column" in value or "不存在" in value:
        return "wrong_field_or_grouping"
    if "semantic" in value or status == "rejected":
        return "semantic_rejection"
    if "timeout" in value:
        return "timeout"
    if "connect" in value:
        return "infrastructure_connection"
    if "json" in value or "unterminated" in value or "expecting" in value:
        return "model_output_parse"
    return "other_execution_or_result_mismatch"


def build() -> tuple[dict[str, Any], str, str]:
    generated_at = datetime.now(timezone.utc).isoformat()
    experiment_ids = ["E00", "E01", "E20", "E21"]
    experiments = {name: load_json(REPORTS / f"{name}.json") for name in experiment_ids}
    for name, report in list(experiments.items()):
        experiment = report.get("experiment", {}) if report else {}
        if (
            experiment.get("dataset") != "data/evaluation/holdout_v2.jsonl"
            or experiment.get("model_max_tokens") != 192
        ):
            experiments[name] = None
    ablation_ids = ["A40", "A41", "A42", "A43", "A44", "A45", "A46", "A47", "A48"]
    ablations = {name: load_json(REPORTS / f"{name}_{suffix}.json") for name, suffix in {
        "A40": "control",
        "A41": "no_few_shot",
        "A42": "no_fk_completion",
        "A43": "full_schema",
        "A44": "one_candidate",
        "A45": "no_repair",
        "A46": "one_repair",
        "A47": "schema_top3",
        "A48": "schema_budget1500",
    }.items()}
    safety = load_json(REPORTS / "safety-ambiguity-v1.json")
    resources = load_json(REPORTS / "inference-resources-v5.json")
    test_suites = {
        name: load_json(REPORTS / f"test-suite-{name}.json")
        for name in experiment_ids
    }
    control_accuracy = metric(ablations["A40"], "execution_accuracy")
    ablation_summary = []
    for name in ablation_ids:
        report = ablations[name]
        accuracy = metric(report, "execution_accuracy")
        ablation_summary.append(
            {
                "id": name,
                "name": report["experiment"].get("name", name) if report else name,
                "complete": report is not None,
                "execution_accuracy": accuracy,
                "delta_vs_control": (
                    accuracy - control_accuracy
                    if accuracy is not None and control_accuracy is not None
                    else None
                ),
                "sql_valid_rate": metric(report, "sql_valid_rate"),
                "repair_gain": metric(report, "repair_gain"),
                "p50_latency_ms": metric(report, "p50_latency_ms"),
                "model_calls": metric(report, "model_calls"),
            }
        )

    summary = {
        "generated_at": generated_at,
        "experiments": {
            name: {
                "complete": report is not None,
                "model": report.get("experiment", {}).get("model") if report else None,
                "strategy": report.get("experiment", {}).get("strategy") if report else None,
                "model_max_tokens": report.get("experiment", {}).get("model_max_tokens") if report else None,
                "sql_valid_rate": metric(report, "sql_valid_rate"),
                "execution_accuracy": metric(report, "execution_accuracy"),
                "p50_latency_ms": metric(report, "p50_latency_ms"),
                "p95_latency_ms": metric(report, "p95_latency_ms"),
                "model_calls": metric(report, "model_calls"),
            }
            for name, report in experiments.items()
        },
        "ablations": ablation_summary,
        "safety": safety.get("safety") if safety else None,
        "clarification": safety.get("clarification") if safety else None,
        "test_suites": {
            name: report.get("summary") if report else None for name, report in test_suites.items()
        },
        "resources": resources.get("measurement") if resources else None,
    }

    lines = [
        "# 最终实验报告",
        "",
        f"生成时间：`{generated_at}`。所有百分比均来自 `experiments/reports` 中的机器可读报告。",
        "",
        "## 严格同预算 2×2",
        "",
        "| 实验 | 模型 | 策略 | Token | SQL 有效率 | 执行准确率 | P50 / P95 | 调用数 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in experiment_ids:
        report = experiments[name]
        item = summary["experiments"][name]
        lines.append(
            "| {id} | {model} | {strategy} | {tokens} | {valid} | {accuracy} | {p50} / {p95} ms | {calls} |".format(
                id=name,
                model=item["model"] or "未完成",
                strategy=item["strategy"] or "—",
                tokens=item["model_max_tokens"] or "—",
                valid=pct(item["sql_valid_rate"]),
                accuracy=pct(item["execution_accuracy"]),
                p50=round(item["p50_latency_ms"] or 0),
                p95=round(item["p95_latency_ms"] or 0),
                calls=item["model_calls"] or 0,
            )
        )
    lines += [
        "",
        "E00/E01 与 E20/E21 使用相同 `holdout_v2`、192 token 和每样本最多 5 次模型调用。",
        "该 Holdout 只有 3 个未见模板族，因此不能把结果外推为任意 Text2SQL 问题的通用准确率。",
        "",
        "## 消融实验",
        "",
        "| 实验 | 状态 | 执行准确率 | 相对 A40 | SQL 有效率 | 修复增益 | P50 | 调用数 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in ablation_summary:
        delta = item["delta_vs_control"]
        lines.append(
            f"| {item['id']} | {'完成' if item['complete'] else '未完成'} | "
            f"{pct(item['execution_accuracy'])} | "
            f"{'—' if delta is None else f'{delta * 100:+.2f} pp'} | "
            f"{pct(item['sql_valid_rate'])} | {item['repair_gain'] if item['repair_gain'] is not None else '—'} | "
            f"{round(item['p50_latency_ms'] or 0)} ms | {item['model_calls'] or 0} |"
        )
    lines += [
        "",
        "## 安全、澄清与多快照 Test-Suite",
        "",
    ]
    if safety:
        combined = safety["safety"]["combined"]
        detection = safety["clarification"]["detection"]
        resolution = safety["clarification"]["resolution"]
        lines += [
            f"- 安全：{combined['correct']}/{combined['total']}，TPR {pct(combined['true_positive_rate'])}，FPR {pct(combined['false_positive_rate'])}。",
            f"- 歧义检测：{detection['correct']}/{detection['total']}，准确率 {pct(detection['accuracy'])}。",
            f"- 澄清后执行：状态 `{resolution['status']}`，执行正确率 {pct(resolution.get('after_execution_accuracy'))}。",
        ]
    for name, report in test_suites.items():
        if report:
            lines.append(
                f"- {name} 三快照 Test-Suite：{pct(report['summary']['test_suite_accuracy'])}，"
                f"{report['summary']['correct_on_all_snapshots']}/{report['summary']['total']} 个样本在所有扰动上均正确。"
            )
    if resources:
        measurement = resources["measurement"]
        lines += [
            "",
            "## 资源",
            "",
            f"- 模型专属 PyTorch CUDA 分配峰值：{measurement['torch_model_cuda_allocated_peak_mb']:.2f} MiB。",
            f"- 端到端系统 GPU 显存峰值：{measurement['system_gpu_memory_peak_mb']:.0f} MiB；该值包含 Windows WDDM 桌面进程。",
            f"- GPU 利用率均值/峰值：{measurement['gpu_utilization_mean_percent']:.2f}% / {measurement['gpu_utilization_peak_percent']:.2f}%。",
        ]
    lines += [
        "",
        "## 结论边界",
        "",
        "- 主结论必须同时引用 300 条未见族 Holdout、81 条 17 模板族消融切片和三快照 Test-Suite。",
        "- 失败与回归不得从平均值中删除；基础设施故障必须单独标记且重跑。",
        "- 本报告不把 Spider/BIRD、跨数据库和多方言列为本期 P0–P5 验收项。",
        "",
    ]

    control = ablations["A40"]
    dataset = {
        row["id"]: row for row in read_jsonl(ROOT / "data/evaluation/dev_v5_ablation81.jsonl")
    }
    group_stats: dict[str, Counter[str]] = defaultdict(Counter)
    buckets: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    if control:
        failed_by_id = {
            row["id"]: row for row in control["summary"].get("failures", [])
        }
        for sample in control["summary"].get("samples", []):
            sample_id = sample["id"]
            group = dataset.get(sample_id, {}).get("template_group", "unknown")
            group_stats[group]["total"] += 1
            group_stats[group]["correct"] += int(sample.get("execution_correct", False))
            if not sample.get("execution_correct", False):
                failure = failed_by_id.get(sample_id, {})
                bucket = failure_bucket(failure.get("error"), failure.get("status"))
                buckets[bucket] += 1
                failures.append(
                    {
                        "id": sample_id,
                        "template_group": group,
                        "bucket": bucket,
                        "status": sample.get("status"),
                        "error": failure.get("error"),
                        "predicted_sql": sample.get("predicted_sql"),
                    }
                )
    badcase_lines = [
        "# Badcase 分类报告",
        "",
        f"生成时间：`{generated_at}`。主要分析 A40 控制组在 81 条、17 个模板族切片上的错误。",
        "",
        "## 错误类型",
        "",
        "| 类型 | 数量 |",
        "| --- | ---: |",
    ]
    for bucket, count in buckets.most_common():
        badcase_lines.append(f"| {bucket} | {count} |")
    badcase_lines += [
        "",
        "## 模板族准确率",
        "",
        "| 模板族 | 正确 | 总数 | 准确率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for group, counts in sorted(group_stats.items()):
        badcase_lines.append(
            f"| {group} | {counts['correct']} | {counts['total']} | "
            f"{pct(counts['correct'] / max(1, counts['total']))} |"
        )
    badcase_lines += [
        "",
        "## 优先处理建议",
        "",
        "1. `wrong_field_or_grouping`：继续补字段归属负例和 GROUP BY 纠错训练样本。",
        "2. `semantic_rejection`：检查候选阈值、Schema 字段召回和唯一 FK 路径归一化。",
        "3. `other_execution_or_result_mismatch`：按模板族核对状态值、时间字段与聚合口径。",
        "4. `infrastructure_connection`：不得计入模型能力结论，恢复数据库后整组重跑。",
        "",
        "完整逐样本记录保存在 `experiments/reports/final-summary.json`。",
        "",
    ]
    summary["badcases"] = {
        "source": "A40",
        "buckets": dict(buckets),
        "template_groups": {group: dict(counts) for group, counts in group_stats.items()},
        "samples": failures,
    }
    return summary, "\n".join(lines), "\n".join(badcase_lines)


def main() -> None:
    summary, final_report, badcase_report = build()
    (ROOT / "docs/experiments").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/experiments/final_report.md").write_text(final_report, encoding="utf-8")
    (ROOT / "docs/experiments/badcase_report.md").write_text(badcase_report, encoding="utf-8")
    (REPORTS / "final-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    complete_ablations = sum(item["complete"] for item in summary["ablations"])
    complete_experiments = sum(item["complete"] for item in summary["experiments"].values())
    print(
        json.dumps(
            {
                "experiments": f"{complete_experiments}/4",
                "ablations": f"{complete_ablations}/9",
                "final_report": "docs/experiments/final_report.md",
                "badcase_report": "docs/experiments/badcase_report.md",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
