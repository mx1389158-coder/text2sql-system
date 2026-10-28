from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional

from apps.api.app.services.orchestrator import Text2SQLOrchestrator

from .metrics import column_recall, execution_equal, exact_match, result_hash, schema_recall
from .safety import SafetyCase, evaluate_safety


@dataclass
class EvaluationSummary:
    total: int
    sql_valid_rate: float
    execution_success_rate: float
    execution_accuracy: float
    test_suite_accuracy: float
    exact_match_rate: float
    schema_recall_at_k: float
    column_recall_at_k: float
    clarification_accuracy: float
    safety_true_positive_rate: float
    safety_false_positive_rate: float
    repair_gain: int
    repairs_fixed: int
    repairs_regressed: int
    p50_latency_ms: float
    p95_latency_ms: float
    wall_time_ms: float
    model_calls: int
    prompt_tokens: int
    completion_tokens: int
    peak_vram_mb: Optional[float]
    failures: List[Dict[str, Any]]
    samples: List[Dict[str, Any]]


class EvaluationRunner:
    def __init__(self, orchestrator: Text2SQLOrchestrator):
        self.orchestrator = orchestrator

    async def run(
        self,
        dataset_path: str | Path,
        strategy: str = "optimized",
        max_model_calls_per_sample: Optional[int] = None,
    ) -> EvaluationSummary:
        examples = self._read_jsonl(dataset_path)
        run_started = time.perf_counter()
        valid = executed = execution_correct = exact = 0
        test_suite_correct = 0
        clarification_correct = 0
        clarification_total = 0
        table_recalls: List[float] = []
        column_recalls: List[float] = []
        latencies: List[float] = []
        failures: List[Dict[str, Any]] = []
        samples: List[Dict[str, Any]] = []
        safety_cases: List[SafetyCase] = []
        repairs_fixed = repairs_regressed = 0
        model_calls = prompt_tokens = completion_tokens = 0
        peak_vram_mb = self._reset_peak_vram()
        for example in examples:
            if "should_allow" in example:
                safety_cases.append(
                    SafetyCase(
                        sql=str(example.get("sql", "")),
                        should_allow=bool(example["should_allow"]),
                        label=str(example.get("id") or example.get("label") or "safety-case"),
                    )
                )
                continue
            started = time.perf_counter()
            record = await self.orchestrator.submit(
                example["question"], strategy=strategy, scope="evaluation"
            )
            latency_ms = (time.perf_counter() - started) * 1000
            latencies.append(latency_ms)
            model_calls += record.model_calls
            prompt_tokens += record.prompt_tokens
            completion_tokens += record.completion_tokens
            repairs_fixed += int(record.repair_succeeded)
            if max_model_calls_per_sample is not None and record.model_calls > max_model_calls_per_sample:
                failures.append(
                    {
                        "id": example.get("id"),
                        "status": "budget_exceeded",
                        "error": f"model calls {record.model_calls}>{max_model_calls_per_sample}",
                    }
                )
            expects_clarification = bool(example.get("clarification"))
            if expects_clarification:
                clarification_total += 1
                clarification_correct += int(record.status.value == "clarification_required")
                samples.append(
                    {
                        "id": example.get("id"),
                        "status": record.status.value,
                        "clarification_correct": record.status.value == "clarification_required",
                        "latency_ms": round(latency_ms, 3),
                        "model_calls": record.model_calls,
                    }
                )
                continue
            if record.sql:
                valid += 1
            if record.result:
                executed += 1
            if example.get("tables") and record.schema_evidence:
                table_recalls.append(
                    schema_recall(record.schema_evidence.selected_tables, example["tables"])
                )
            if example.get("columns") and record.schema_evidence:
                column_recalls.append(
                    column_recall(record.schema_evidence.selected_columns, example["columns"])
                )
            gold_sqls = example.get("gold_sqls") or ([example["sql"]] if example.get("sql") else [])
            sample_execution_correct = False
            sample_test_suite_correct = False
            if gold_sqls and record.sql:
                exact += int(any(exact_match(record.sql, sql) for sql in gold_sqls))
                for gold_sql in gold_sqls:
                    try:
                        guarded = self.orchestrator.guard.validate_and_rewrite(str(gold_sql))
                        gold_result = self.orchestrator.runner.execute(guarded.sql)
                        if record.result and gold_result.ok and execution_equal(
                            record.result.rows,
                            gold_result.rows,
                            bool(example.get("order_sensitive", False)),
                        ):
                            sample_execution_correct = True
                            sample_test_suite_correct = True
                            break
                    except Exception:
                        continue
            expected_hash = example.get("expected_result_hash")
            if expected_hash and record.result:
                sample_execution_correct = result_hash(
                    record.result.rows, bool(example.get("order_sensitive", False))
                ) == str(expected_hash)
                sample_test_suite_correct = sample_execution_correct
            execution_correct += int(sample_execution_correct)
            test_suite_correct += int(sample_test_suite_correct)
            if record.status.value not in {"completed", "clarification_required"}:
                failures.append(
                    {
                        "id": example.get("id"),
                        "status": record.status.value,
                        "error": record.error_message,
                    }
                )
            samples.append(
                {
                    "id": example.get("id"),
                    "status": record.status.value,
                    "predicted_sql": record.sql,
                    "execution_correct": sample_execution_correct,
                    "test_suite_correct": sample_test_suite_correct,
                    "repair_rounds": record.repair_rounds,
                    "repair_succeeded": record.repair_succeeded,
                    "latency_ms": round(latency_ms, 3),
                    "model_calls": record.model_calls,
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                }
            )
        safety_report = evaluate_safety(self.orchestrator.guard, safety_cases)
        total = len(examples) - len(safety_cases)
        query_total = max(1, total - clarification_total)
        ordered = sorted(latencies)
        p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
        current_peak = self._peak_vram()
        if current_peak is not None:
            peak_vram_mb = max(peak_vram_mb or 0.0, current_peak)
        return EvaluationSummary(
            total=total,
            sql_valid_rate=valid / query_total,
            execution_success_rate=executed / query_total,
            execution_accuracy=execution_correct / query_total,
            test_suite_accuracy=test_suite_correct / query_total,
            exact_match_rate=exact / query_total,
            schema_recall_at_k=sum(table_recalls) / max(1, len(table_recalls)),
            column_recall_at_k=sum(column_recalls) / max(1, len(column_recalls)),
            clarification_accuracy=clarification_correct / max(1, clarification_total),
            safety_true_positive_rate=safety_report.true_positive_rate,
            safety_false_positive_rate=safety_report.false_positive_rate,
            repair_gain=repairs_fixed - repairs_regressed,
            repairs_fixed=repairs_fixed,
            repairs_regressed=repairs_regressed,
            p50_latency_ms=median(latencies) if latencies else 0,
            p95_latency_ms=ordered[p95_index] if ordered else 0,
            wall_time_ms=(time.perf_counter() - run_started) * 1000,
            model_calls=model_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            peak_vram_mb=peak_vram_mb,
            failures=failures,
            samples=samples,
        )

    @staticmethod
    def _reset_peak_vram() -> Optional[float]:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
                return 0.0
        except ImportError:
            pass
        return None

    @staticmethod
    def _peak_vram() -> Optional[float]:
        try:
            import torch

            if torch.cuda.is_available():
                return torch.cuda.max_memory_allocated() / (1024 * 1024)
        except ImportError:
            pass
        return None

    @staticmethod
    def _read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
        with Path(path).open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    @staticmethod
    def write(summary: EvaluationSummary, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            json.dump(asdict(summary), handle, ensure_ascii=False, indent=2)

