from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import replace
from typing import Callable, List, Optional

from packages.execution.access import AccessPolicy
from packages.execution.guard import SQLGuard, SQLSafetyError
from packages.execution.runner import DatabaseRunner, ExecutionResult
from packages.generation.candidates import (
    CandidateGenerator,
    CandidateSelector,
    LightweightCandidateScorer,
)
from packages.generation.few_shot import FewShotRetriever
from packages.generation.governed_metrics import GovernedMetricCompiler
from packages.generation.models import CandidateScore, GenerationRequest
from packages.generation.prompts import SYSTEM_PROMPT_VERSION, build_repair_feedback
from packages.generation.providers import ProviderGenerationError
from packages.schema_linker.mschema import MSchemaFormatter
from packages.schema_linker.models import DatabaseCatalog, SchemaEvidence
from packages.schema_linker.retriever import SchemaRetriever
from packages.schema_linker.semantic_catalog import SemanticCatalog

from ..core.config import Settings
from ..repositories import QueryRepository
from ..schemas.query import (
    Clarification,
    Intent,
    QueryRecord,
    QueryResult,
    QueryStatus,
    SchemaEvidenceResponse,
    Strategy,
    TraceEvent,
)
from .cache import (
    CachedQueryResult,
    QueryCache,
    TTLCache,
    normalize_question,
    stable_cache_key,
)
from .intent import IntentClassifier
from .observability import ObservabilitySink


class Text2SQLOrchestrator:
    def __init__(
        self,
        settings: Settings,
        catalog: DatabaseCatalog,
        semantic_catalog: SemanticCatalog,
        generator: CandidateGenerator,
        guard: SQLGuard,
        runner: DatabaseRunner,
        repository: QueryRepository,
        access_policy: Optional[AccessPolicy] = None,
    ):
        self.settings = settings
        self.catalog = catalog
        self.semantic_catalog = semantic_catalog
        self.generator = generator
        self.guard = guard
        self.runner = runner
        self.repository = repository
        self.access_policy = access_policy or AccessPolicy(
            {},
            {table.name for table in catalog.tables},
            catalog.schema,
            version="missing-deny-all",
        )
        self.intent = IntentClassifier()
        self.retriever = SchemaRetriever(catalog, dense_weight=settings.schema_dense_weight)
        self.formatter = MSchemaFormatter(catalog)
        self.cache = QueryCache(settings.cache_ttl_seconds)
        self.schema_cache: TTLCache[SchemaEvidence] = TTLCache(settings.schema_cache_ttl_seconds)
        self.few_shot_cache: TTLCache[List[str]] = TTLCache(settings.schema_cache_ttl_seconds)
        self.few_shots = FewShotRetriever(settings.few_shot_path, settings.few_shot_count)
        self.observability = ObservabilitySink(settings)
        self.candidate_scorer = LightweightCandidateScorer(catalog)
        self.metric_compiler = GovernedMetricCompiler()

    async def submit(
        self,
        question: str,
        session_id: Optional[str] = None,
        strategy: Strategy = "optimized",
        clarification_answer: Optional[str] = None,
        existing_query_id: Optional[str] = None,
        scope: str = "default",
        trace_listener: Optional[Callable[[TraceEvent], None]] = None,
    ) -> QueryRecord:
        record = QueryRecord(
            query_id=existing_query_id or str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            scope=scope,
            session_id=session_id,
            question=question.strip(),
            clarification_answer=clarification_answer,
            strategy=strategy,
            model=self.settings.llm_model if self.settings.llm_provider != "demo" else "demo-rules",
            prompt_version=SYSTEM_PROMPT_VERSION,
        )
        self.repository.save(record)
        scope_policy = self.access_policy.resolve(scope)
        stage_started = time.perf_counter()
        decision = self.intent.classify(record.question)
        record.intent = decision.intent
        self._trace(
            record,
            "intent",
            "completed",
            stage_started,
            {"intent": decision.intent.value},
            trace_listener,
        )
        if decision.intent == Intent.REJECT:
            record.status = QueryStatus.REJECTED
            record.error_code = "request_rejected"
            record.error_message = decision.reason
            return self.repository.save(record)
        if decision.intent == Intent.META:
            record.status = QueryStatus.COMPLETED
            record.explanation = self._catalog_explanation(scope_policy.tables)
            return self.repository.save(record)

        ambiguity = self.semantic_catalog.ambiguity(record.question)
        if ambiguity and not clarification_answer:
            record.intent = Intent.CLARIFY
            record.status = QueryStatus.CLARIFICATION_REQUIRED
            record.clarification = Clarification(**ambiguity)
            self._trace(
                record,
                "clarification",
                "required",
                time.perf_counter(),
                ambiguity,
                trace_listener,
            )
            return self.repository.save(record)

        semantic_items = self.semantic_catalog.retrieve(record.question)
        semantic_lines = [
            f"[{item.key}@{item.version}] {item.name}: {item.definition}" for item in semantic_items
        ]
        cache_key = self.cache.key(
            question=record.question,
            clarification=clarification_answer or "",
            schema_version=self.catalog.version,
            scope=scope,
            policy_version=self.access_policy.version,
            strategy=strategy,
            model_id=record.model or "unknown",
            prompt_version=record.prompt_version or "unversioned",
            few_shot_version=self.few_shots.version,
            semantic_version=self.semantic_catalog.version,
            runtime_version=self._runtime_cache_version(strategy),
        )
        cached = self.cache.get(cache_key)
        if cached:
            cached.apply_to(record)
            record.cached = True
            self._trace(record, "cache", "hit", time.perf_counter(), {}, trace_listener)
            return self.repository.save(record)

        stage_started = time.perf_counter()
        scoped_columns = {
            table: scope_policy.allowed_columns(
                table,
                set(self.guard.policy.allowed_columns.get(table, set())),
            )
            for table in scope_policy.tables
        }
        query_guard = SQLGuard(
            replace(
                self.guard.policy,
                allowed_tables=set(scope_policy.tables),
                allowed_columns=scoped_columns,
                allowed_schemas=set(scope_policy.schemas),
                deny_select_star=bool(scope_policy.columns),
            )
        )
        top_k = len(self.catalog.tables) if strategy == "baseline" else self.settings.schema_top_k
        schema_key = stable_cache_key(
            "schema-evidence-v2",
            normalized_question=normalize_question(record.question),
            normalized_clarification=normalize_question(clarification_answer or ""),
            scope=scope,
            policy_version=self.access_policy.version,
            schema_version=self.catalog.version,
            strategy=strategy,
            top_k=top_k,
            max_top_k=self.settings.schema_max_top_k,
            dense_weight=self.settings.schema_dense_weight,
            fk_completion=self.settings.enable_fk_completion,
            adaptive_schema=self.settings.enable_adaptive_schema,
            token_budget=(
                16000 if strategy == "baseline" else self.settings.schema_token_budget
            ),
        )
        evidence = self.schema_cache.get(schema_key)
        schema_cache_hit = evidence is not None
        if evidence is None:
            evidence = self.retriever.retrieve(
                record.question,
                top_k=top_k,
                expand_join_paths=(
                    strategy != "baseline" and self.settings.enable_fk_completion
                ),
                expand_if_low_confidence=(
                    strategy != "baseline" and self.settings.enable_adaptive_schema
                ),
                max_top_k=self.settings.schema_max_top_k,
            )
            allowed = set(scope_policy.tables)
            evidence = replace(
                evidence,
                selected_tables=[name for name in evidence.selected_tables if name in allowed],
                selected_columns=[
                    item
                    for item in evidence.selected_columns
                    if item.table in allowed
                    and item.column in scoped_columns.get(item.table, set())
                ],
                join_path_tables=[name for name in evidence.join_path_tables if name in allowed],
                table_scores={
                    name: score for name, score in evidence.table_scores.items() if name in allowed
                },
            )
            evidence = self.formatter.format(
                evidence,
                token_budget=(
                    16000 if strategy == "baseline" else self.settings.schema_token_budget
                ),
                allowed_columns=scoped_columns,
                sample_value_allowed=scope_policy.allows_sample_value,
            )
            self.schema_cache.set(schema_key, evidence)
        record.schema_evidence = self._schema_response(evidence, semantic_lines)
        self._trace(
            record,
            "schema_linking",
            "completed",
            stage_started,
            {
                "tables": evidence.selected_tables,
                "tokens": evidence.estimated_tokens,
                "confidence": evidence.confidence,
                "expanded": evidence.expanded,
                "cache_hit": schema_cache_hit,
            },
            trace_listener,
        )

        few_shot_key = stable_cache_key(
            "few-shot-v2",
            normalized_question=normalize_question(record.question),
            scope=scope,
            policy_version=self.access_policy.version,
            schema_version=self.catalog.version,
            strategy=strategy,
            few_shot_version=self.few_shots.version,
            selected_tables=evidence.selected_tables,
            enabled=self.settings.enable_few_shots,
        )
        few_shots = (
            []
            if strategy == "baseline" or not self.settings.enable_few_shots
            else self.few_shot_cache.get(few_shot_key)
        )
        if few_shots is None:
            few_shots = self.few_shots.retrieve(record.question, evidence.selected_tables)
            self.few_shot_cache.set(few_shot_key, few_shots)

        generation_request = GenerationRequest(
            question=record.question,
            clarification=clarification_answer,
            mschema=evidence.mschema,
            semantic_definitions=semantic_lines,
            few_shots=few_shots,
        )
        count = 1 if strategy == "baseline" else self.settings.candidate_count
        stage_started = time.perf_counter()
        governed_candidate = None
        if ambiguity and clarification_answer:
            governed_candidate = self.metric_compiler.compile(
                record.question,
                str(ambiguity["key"]),
                clarification_answer,
            )
        try:
            candidates = (
                [governed_candidate]
                if governed_candidate is not None
                else await self.generator.generate(generation_request, count=count)
            )
        except ProviderGenerationError as error:
            record.model_calls += error.provider_calls
            record.prompt_tokens += error.prompt_tokens
            record.completion_tokens += error.completion_tokens
            record.status = QueryStatus.FAILED
            record.error_code = "model_response_error"
            record.error_message = str(error)[:500]
            self._trace(
                record,
                "generation",
                "failed",
                stage_started,
                {
                    "error": record.error_message,
                    "provider_calls": error.provider_calls,
                },
                trace_listener,
            )
            return self.repository.save(record)
        except Exception as error:
            record.status = QueryStatus.FAILED
            record.error_code = "model_error"
            record.error_message = str(error)[:500]
            self._trace(
                record,
                "generation",
                "failed",
                stage_started,
                {"error": record.error_message},
                trace_listener,
            )
            return self.repository.save(record)
        record.model_calls += sum(item.provider_calls for item in candidates)
        record.prompt_tokens += sum(item.prompt_tokens for item in candidates)
        record.completion_tokens += sum(item.completion_tokens for item in candidates)
        self._trace(
            record,
            "generation",
            "completed",
            stage_started,
            {
                "candidates": len(candidates),
                "few_shots": len(few_shots),
                "source": (
                    "governed_metric_compiler"
                    if governed_candidate is not None
                    else "model"
                ),
                "prompt_version": record.prompt_version,
            },
            trace_listener,
        )

        scores: List[CandidateScore] = []
        guarded_sql = {}
        execution_results = {}
        for candidate in candidates:
            if strategy != "baseline":
                normalized_sql = self.candidate_scorer.normalize_known_field_aliases(
                    candidate.sql
                )
                normalized_sql = self.candidate_scorer.normalize_unique_fk_joins(
                    normalized_sql
                )
                if normalized_sql != candidate.sql:
                    candidate = replace(
                        candidate,
                        sql=normalized_sql,
                        assumptions=[
                            *candidate.assumptions,
                            "normalized an unambiguous catalog FK join path",
                        ],
                    )
            try:
                guarded = query_guard.validate_and_rewrite(candidate.sql)
                guarded_sql[candidate.sql] = guarded.sql
                coverage = len(set(guarded.referenced_tables) & set(evidence.selected_tables)) / max(
                    1, len(guarded.referenced_tables)
                )
                result = await asyncio.to_thread(self.runner.execute, guarded.sql)
                execution_results[candidate.sql] = result
                scores.append(
                    CandidateScore(
                        candidate=candidate,
                        static_valid=True,
                        schema_coverage=coverage,
                        executed=result.ok,
                        non_empty=bool(result.rows),
                        execution_ms=result.elapsed_ms,
                        error=result.error.safe_message if result.error else None,
                        semantic_score=(
                            1.0
                            if governed_candidate is not None
                            else self.candidate_scorer.score(record.question, candidate)
                        ),
                    )
                )
            except SQLSafetyError as error:
                scores.append(
                    CandidateScore(
                        candidate=candidate,
                        static_valid=False,
                        schema_coverage=0,
                        error=error.reason,
                        semantic_score=(
                            1.0
                            if governed_candidate is not None
                            else self.candidate_scorer.score(record.question, candidate)
                        ),
                    )
                )
        self._trace(
            record,
            "candidate_selection",
            "completed",
            time.perf_counter(),
            {
                "candidates": [
                    {
                        "sql": score.candidate.sql,
                        "static_valid": score.static_valid,
                        "executed": score.executed,
                        "non_empty": score.non_empty,
                        "schema_coverage": score.schema_coverage,
                        "semantic_score": score.semantic_score,
                        "error": score.error,
                    }
                    for score in scores
                ]
            },
            trace_listener,
        )
        chosen = CandidateSelector.choose(scores)
        repair_rounds = 0
        repair_limit = 0 if governed_candidate is not None else self.settings.max_repair_rounds
        initial_candidate_acceptable = bool(
            chosen.static_valid
            and chosen.executed
            and chosen.semantic_score >= self.settings.candidate_semantic_threshold
        )
        while (
            strategy != "baseline"
            and repair_rounds < repair_limit
            and (
                not chosen.static_valid
                or chosen.semantic_score < self.settings.candidate_semantic_threshold
            )
        ):
            repair_rounds += 1
            requirements = self.candidate_scorer.feedback(record.question, chosen.candidate)
            feedback = build_repair_feedback(
                "static_validation" if not chosen.static_valid else "semantic_mismatch",
                (
                    f"{chosen.error or '候选未覆盖问题关键语义'}。"
                    f"必须修正：{requirements}。上一候选 SQL：{chosen.candidate.sql}"
                ),
            )
            repair_request = GenerationRequest(
                question=record.question,
                clarification=clarification_answer,
                mschema=evidence.mschema,
                semantic_definitions=semantic_lines,
                few_shots=few_shots,
                error_feedback=feedback,
            )
            try:
                repaired = await self.generator.generate(repair_request, count=1)
            except ProviderGenerationError as error:
                record.model_calls += error.provider_calls
                record.prompt_tokens += error.prompt_tokens
                record.completion_tokens += error.completion_tokens
                break
            record.model_calls += sum(item.provider_calls for item in repaired)
            record.prompt_tokens += sum(item.prompt_tokens for item in repaired)
            record.completion_tokens += sum(item.completion_tokens for item in repaired)
            repaired_candidate = repaired[0]
            normalized_sql = self.candidate_scorer.normalize_known_field_aliases(
                repaired_candidate.sql
            )
            normalized_sql = self.candidate_scorer.normalize_unique_fk_joins(
                normalized_sql
            )
            if normalized_sql != repaired_candidate.sql:
                repaired_candidate = replace(repaired_candidate, sql=normalized_sql)
            repaired_semantic_score = self.candidate_scorer.score(
                record.question, repaired_candidate
            )
            try:
                guarded = query_guard.validate_and_rewrite(repaired_candidate.sql)
                result = await asyncio.to_thread(self.runner.execute, guarded.sql)
                guarded_sql[repaired_candidate.sql] = guarded.sql
                execution_results[repaired_candidate.sql] = result
                coverage = len(
                    set(guarded.referenced_tables) & set(evidence.selected_tables)
                ) / max(1, len(guarded.referenced_tables))
                chosen = CandidateScore(
                    candidate=repaired_candidate,
                    static_valid=True,
                    schema_coverage=coverage,
                    executed=result.ok,
                    non_empty=bool(result.rows),
                    execution_ms=result.elapsed_ms,
                    error=result.error.safe_message if result.error else None,
                    semantic_score=repaired_semantic_score,
                )
            except SQLSafetyError as error:
                chosen = CandidateScore(
                    candidate=repaired_candidate,
                    static_valid=False,
                    schema_coverage=0,
                    error=error.reason,
                    semantic_score=repaired_semantic_score,
                )
        if not chosen.static_valid:
            record.status = QueryStatus.REJECTED
            record.error_code = "unsafe_model_output"
            record.error_message = chosen.error
            self._trace(
                record,
                "safety",
                "rejected",
                time.perf_counter(),
                {"reason": chosen.error},
                trace_listener,
            )
            return self.repository.save(record)
        if (
            strategy != "baseline"
            and chosen.semantic_score < self.settings.candidate_semantic_threshold
        ):
            record.status = QueryStatus.REJECTED
            record.error_code = "semantic_mismatch"
            record.error_message = (
                "候选 SQL 未覆盖问题中的关键业务实体、字段或时间方向"
            )
            self._trace(
                record,
                "candidate_selection",
                "rejected",
                time.perf_counter(),
                {
                    "semantic_score": chosen.semantic_score,
                    "threshold": self.settings.candidate_semantic_threshold,
                },
                trace_listener,
            )
            record.repair_rounds = repair_rounds
            return self.repository.save(record)

        final_candidate = chosen.candidate
        final_sql = guarded_sql[final_candidate.sql]
        execution = execution_results[final_candidate.sql]
        if execution.error is not None and execution.error.category.value == "timeout":
            repair_limit = min(repair_limit, 1)
        while (
            not execution.ok
            and strategy != "baseline"
            and execution.error is not None
            and execution.error.repairable
            and repair_rounds < repair_limit
        ):
            repair_rounds += 1
            feedback = build_repair_feedback(
                execution.error.category.value,
                execution.error.safe_message,
                allowed_hint=evidence.mschema,
            )
            repair_request = GenerationRequest(
                question=record.question,
                clarification=clarification_answer,
                mschema=evidence.mschema,
                semantic_definitions=semantic_lines,
                few_shots=few_shots,
                error_feedback=feedback,
            )
            repaired = await self.generator.generate(repair_request, count=1)
            record.model_calls += sum(item.provider_calls for item in repaired)
            record.prompt_tokens += sum(item.prompt_tokens for item in repaired)
            record.completion_tokens += sum(item.completion_tokens for item in repaired)
            repaired_candidate = repaired[0]
            normalized_sql = self.candidate_scorer.normalize_known_field_aliases(
                repaired_candidate.sql
            )
            normalized_sql = self.candidate_scorer.normalize_unique_fk_joins(
                normalized_sql
            )
            if normalized_sql != repaired_candidate.sql:
                repaired_candidate = replace(repaired_candidate, sql=normalized_sql)
            try:
                guarded = query_guard.validate_and_rewrite(repaired_candidate.sql)
            except SQLSafetyError:
                break
            final_candidate = repaired_candidate
            final_sql = guarded.sql
            execution = await asyncio.to_thread(self.runner.execute, final_sql)
        record.repair_rounds = repair_rounds
        record.repair_succeeded = bool(
            repair_rounds and not initial_candidate_acceptable and execution.ok
        )
        record.sql = final_sql
        record.assumptions = final_candidate.assumptions
        self._trace(
            record,
            "execution",
            "completed" if execution.ok else "failed",
            time.perf_counter() - execution.elapsed_ms / 1000,
            {
                "rows": len(execution.rows),
                "repair_rounds": repair_rounds,
                "repair_succeeded": record.repair_succeeded,
            },
            trace_listener,
        )
        if not execution.ok:
            record.status = QueryStatus.FAILED
            record.error_code = execution.error.category.value if execution.error else "execution_error"
            record.error_message = execution.error.safe_message if execution.error else "执行失败"
            return self.repository.save(record)

        record.result = QueryResult(
            columns=execution.columns,
            rows=execution.rows,
            truncated=execution.truncated,
            elapsed_ms=round(execution.elapsed_ms, 3),
        )
        record.explanation = self._explain(execution)
        record.status = QueryStatus.COMPLETED
        record.intent = Intent.QUERY
        self._trace(
            record, "explanation", "completed", time.perf_counter(), {}, trace_listener
        )
        self.repository.save(record)
        self.cache.set(cache_key, CachedQueryResult.from_record(record))
        return record

    @staticmethod
    def _schema_response(evidence: SchemaEvidence, semantic_lines: List[str]) -> SchemaEvidenceResponse:
        return SchemaEvidenceResponse(
            selected_tables=evidence.selected_tables,
            join_path_tables=evidence.join_path_tables,
            table_scores=evidence.table_scores,
            mschema=evidence.mschema,
            estimated_tokens=evidence.estimated_tokens,
            semantic_definitions=semantic_lines,
            selected_columns=[
                f"{item.table}.{item.column}" for item in evidence.selected_columns
            ],
            confidence=evidence.confidence,
            expanded=evidence.expanded,
        )

    def _catalog_explanation(self, allowed_tables: set[str]) -> str:
        summaries = [
            f"{table.name}（{table.description}）"
            for table in self.catalog.tables
            if table.name in allowed_tables
        ]
        if not summaries:
            return "当前权限域没有可访问的数据库表。"
        return f"数据库目录版本 {self.catalog.version}，共 {len(summaries)} 张表：" + "、".join(summaries)

    def _runtime_cache_version(self, strategy: Strategy) -> str:
        return stable_cache_key(
            "runtime-config-v1",
            strategy=strategy,
            candidate_count=(1 if strategy == "baseline" else self.settings.candidate_count),
            max_repair_rounds=(
                0 if strategy == "baseline" else self.settings.max_repair_rounds
            ),
            semantic_threshold=self.settings.candidate_semantic_threshold,
            model_max_tokens=self.settings.model_max_tokens,
            max_rows=self.settings.max_rows,
        )

    @staticmethod
    def _explain(result: ExecutionResult) -> str:
        if not result.rows:
            return "查询执行成功，但在当前固定快照与口径下结果为空；系统未自动放宽筛选条件。"
        suffix = "，结果已按安全上限截断" if result.truncated else ""
        return f"查询执行成功，返回 {len(result.rows)} 行，字段为：{', '.join(result.columns)}{suffix}。"

    def _trace(
        self,
        record: QueryRecord,
        stage: str,
        status: str,
        started: float,
        detail: dict,
        listener: Optional[Callable[[TraceEvent], None]] = None,
    ) -> None:
        event = TraceEvent(
            stage=stage,
            status=status,
            elapsed_ms=round(max(0.0, (time.perf_counter() - started) * 1000), 3),
            detail=detail,
        )
        record.trace.append(event)
        self.observability.emit(record, event)
        if listener is not None:
            listener(event)

