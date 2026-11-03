from __future__ import annotations

import re
from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Set, Tuple

import sqlglot
from sqlglot import exp

from .models import CandidateScore, GeneratedCandidate, GenerationRequest
from .providers import SQLProvider
from packages.schema_linker.models import DatabaseCatalog
from packages.schema_linker.vector import HashingTextEncoder


class CandidateGenerator:
    def __init__(self, provider: SQLProvider):
        self.provider = provider

    async def generate(self, request: GenerationRequest, count: int = 1) -> List[GeneratedCandidate]:
        candidates = [await self.provider.generate(request, temperature=0.0)]
        if count > 1:
            candidates.extend(
                await self.provider.generate_many(
                    request,
                    temperature=0.2,
                    count=count - 1,
                )
            )
        return self._deduplicate(candidates)

    @staticmethod
    def _deduplicate(candidates: Iterable[GeneratedCandidate]) -> List[GeneratedCandidate]:
        unique = {}
        for candidate in candidates:
            normalized = " ".join(candidate.sql.lower().split())
            existing = unique.get(normalized)
            if existing is None:
                unique[normalized] = candidate
            else:
                unique[normalized] = replace(
                    existing,
                    provider_calls=existing.provider_calls + candidate.provider_calls,
                    prompt_tokens=existing.prompt_tokens + candidate.prompt_tokens,
                    completion_tokens=existing.completion_tokens + candidate.completion_tokens,
                )
        return list(unique.values())


class CandidateSelector:
    @staticmethod
    def choose(scores: List[CandidateScore]) -> CandidateScore:
        if not scores:
            raise ValueError("没有可选择的 SQL 候选")
        return max(
            scores,
            key=lambda item: (
                item.static_valid,
                item.executed,
                item.semantic_score,
                item.schema_coverage,
                item.non_empty,
                -item.execution_ms,
            ),
        )


class LightweightCandidateScorer:
    _QUESTION_MARKERS = {
        "型号": ("model_code", "products"),
        "产品": ("products", "product_id"),
        "团队": ("teams", "team_id"),
        "工程师": ("agents", "agent_id", "assigned_agent_id"),
        "服务人员": ("agents", "agent_id", "assigned_agent_id"),
        "固件": ("firmware_versions", "firmware_id"),
        "版本": ("version", "firmware_versions"),
        "保修": ("warranties", "starts_at", "ends_at"),
        "质保": ("warranties", "starts_at", "ends_at"),
        "上门": ("service_visits",),
        "满意": ("satisfaction_surveys", "score"),
        "评分": ("score",),
        "库存": ("inventory", "quantity"),
        "地区": ("regions", "region_id"),
        "订单": ("orders", "order_id"),
        "支付": ("payments", "paid_at"),
        "退款": ("refunds", "refund_type"),
        "工单": ("tickets", "ticket_id"),
        "配送": ("shipments", "delivered_at"),
        "送达": ("shipments", "delivered_at"),
        "升级": ("device_upgrades", "upgraded_at"),
        "分类": ("product_categories", "category_id"),
        "品类": ("product_categories", "category_id"),
    }

    _STATUS_MARKERS = {
        "获批": "approved",
        "失败": "failed",
        "已送达": "delivered",
    }
    _FIELD_ALIASES = {
        ("refunds", "refund_status"): "status",
        ("refunds", "refunded_at"): "created_at",
    }

    def __init__(self, catalog: Optional[DatabaseCatalog] = None):
        self.encoder = HashingTextEncoder()
        self.foreign_keys: Set[frozenset[Tuple[str, str]]] = set()
        if catalog is not None:
            for table in catalog.tables:
                for foreign_key in table.foreign_keys:
                    self.foreign_keys.add(
                        frozenset(
                            {
                                (table.name.lower(), foreign_key.column.lower()),
                                (
                                    foreign_key.referred_table.lower(),
                                    foreign_key.referred_column.lower(),
                                ),
                            }
                        )
                    )

    def score(self, question: str, candidate: GeneratedCandidate) -> float:
        evidence = " ".join(
            [candidate.sql, *candidate.used_tables, *candidate.assumptions]
        )
        lexical = max(
            0.0,
            self.encoder.cosine(
                self.encoder.encode(question), self.encoder.encode(evidence)
            ),
        )
        sql = candidate.sql.lower()
        checks = [
            any(marker in sql for marker in sql_markers)
            for question_marker, sql_markers in self._QUESTION_MARKERS.items()
            if question_marker in question
        ]
        if any(marker in question for marker in ("以来", "之后", "起")):
            checks.append(">=" in sql or " > " in sql)
        if any(marker in question for marker in ("截至", "之前", "以前", "前")):
            checks.append("<=" in sql or " < " in sql)
        checks.extend(
            self._has_status_filter(sql, status)
            for marker, status in self._STATUS_MARKERS.items()
            if marker in question
        )
        # An empty marker set means that the lightweight rules have no evidence
        # of a mismatch.  Treat it as neutral-positive instead of forcing every
        # new business phrase below the repair threshold.
        intent_alignment = sum(checks) / len(checks) if checks else 1.0
        if any(
            marker in question and not self._has_status_filter(sql, status)
            for marker, status in self._STATUS_MARKERS.items()
        ):
            intent_alignment = min(intent_alignment, 0.4)
        compound_mismatches = self._compound_mismatches(question, sql)
        if compound_mismatches:
            intent_alignment = min(intent_alignment, 0.4)
        join_alignment = self._join_alignment(candidate.sql)
        score = 0.15 * lexical + 0.55 * intent_alignment + 0.30 * join_alignment
        # A join that contradicts every declared FK can execute and return
        # plausible rows, but it is not a valid semantic candidate.
        if join_alignment < 1.0:
            score = min(score, 0.4)
        return round(score, 4)

    def feedback(self, question: str, candidate: GeneratedCandidate) -> str:
        sql = candidate.sql.lower()
        missing = [
            question_marker
            for question_marker, sql_markers in self._QUESTION_MARKERS.items()
            if question_marker in question
            and not any(marker in sql for marker in sql_markers)
        ]
        if any(marker in question for marker in ("以来", "之后", "起")):
            if ">=" not in sql and " > " not in sql:
                missing.append("起始时间方向(>=)")
        if any(marker in question for marker in ("截至", "之前", "以前", "前")):
            if "<=" not in sql and " < " not in sql:
                missing.append("截止时间方向(<=)")
        missing.extend(
            f"状态筛选({status})"
            for marker, status in self._STATUS_MARKERS.items()
            if marker in question and not self._has_status_filter(sql, status)
        )
        if self._join_alignment(candidate.sql) < 1.0:
            paths = self._relevant_fk_paths(candidate.sql)
            suffix = "；".join(paths)
            missing.append(
                f"目录中声明的外键连接路径（仅使用：{suffix}）"
                if suffix
                else "目录中声明的外键连接路径"
            )
        missing.extend(self._compound_mismatches(question, sql))
        return "、".join(dict.fromkeys(missing)) or "问题中的业务实体、字段与时间方向"

    @staticmethod
    def _compound_mismatches(question: str, sql: str) -> List[str]:
        missing: List[str] = []
        if "地区" in question and any(marker in question for marker in ("送达", "配送")):
            required = ("shipments", "customer_addresses", "address_id", "region_id")
            if not all(marker in sql for marker in required):
                missing.append(
                    "配送地区路径(shipments.address_id→customer_addresses.region_id→regions.id)"
                )
        return missing

    def _join_alignment(self, sql: str) -> float:
        if not self.foreign_keys:
            return 0.5
        try:
            root = sqlglot.parse_one(sql, read="postgres")
        except sqlglot.errors.ParseError:
            return 0.0
        aliases: Dict[str, str] = {
            table.alias_or_name.lower(): table.name.lower()
            for table in root.find_all(exp.Table)
        }
        cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
        cte_aliases = {
            table.alias_or_name.lower()
            for table in root.find_all(exp.Table)
            if table.name.lower() in cte_names
        }
        joins = list(root.find_all(exp.Join))
        if not joins:
            return 1.0
        valid = 0
        for join in joins:
            on_expression = join.args.get("on")
            if on_expression is None:
                continue
            if any(
                column.table and column.table.lower() in cte_aliases
                for column in on_expression.find_all(exp.Column)
            ):
                # The CTE output lineage has already been checked by SQLGuard,
                # but it is not a physical catalog FK endpoint. Treat it as
                # neutral-valid instead of inventing a replacement join.
                valid += 1
                continue
            if any(
                self._is_foreign_key_equality(equality, aliases)
                for equality in on_expression.find_all(exp.EQ)
            ):
                valid += 1
        return valid / len(joins)

    def _relevant_fk_paths(self, sql: str) -> List[str]:
        try:
            root = sqlglot.parse_one(sql, read="postgres")
        except sqlglot.errors.ParseError:
            return []
        tables = {table.name.lower() for table in root.find_all(exp.Table)}
        paths = []
        for foreign_key in self.foreign_keys:
            endpoints = sorted(foreign_key)
            if len(endpoints) != 2 or not all(table in tables for table, _ in endpoints):
                continue
            left, right = endpoints
            paths.append(f"{left[0]}.{left[1]}={right[0]}.{right[1]}")
        if not paths and len(tables) > 1:
            graph: Dict[str, List[Tuple[str, frozenset[Tuple[str, str]]]]] = {}
            for foreign_key in self.foreign_keys:
                endpoints = list(foreign_key)
                if len(endpoints) != 2:
                    continue
                left, right = endpoints
                graph.setdefault(left[0], []).append((right[0], foreign_key))
                graph.setdefault(right[0], []).append((left[0], foreign_key))
            ordered_tables = sorted(tables)
            source = ordered_tables[0]
            for target in ordered_tables[1:]:
                queue = [(source, [])]
                visited = {source}
                while queue:
                    current, edges = queue.pop(0)
                    if current == target:
                        for edge in edges:
                            left, right = sorted(edge)
                            paths.append(
                                f"{left[0]}.{left[1]}={right[0]}.{right[1]}"
                            )
                        break
                    for neighbor, edge in graph.get(current, []):
                        if neighbor not in visited and len(edges) < 4:
                            visited.add(neighbor)
                            queue.append((neighbor, [*edges, edge]))
        return sorted(paths)

    def normalize_unique_fk_joins(self, sql: str) -> str:
        """Repair only unambiguous direct or single-bridge catalog joins."""
        if not self.foreign_keys:
            return sql
        try:
            root = sqlglot.parse_one(sql, read="postgres")
        except sqlglot.errors.ParseError:
            return sql
        from_expression = root.args.get("from_")
        joins = list(root.args.get("joins") or [])
        if from_expression is None or not joins:
            return sql
        base_tables = list(from_expression.find_all(exp.Table))
        if len(base_tables) != 1:
            return sql
        base = base_tables[0]
        cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
        cte_aliases = {
            table.alias_or_name.lower()
            for table in root.find_all(exp.Table)
            if table.name.lower() in cte_names
        }
        introduced: Dict[str, str] = {base.name.lower(): base.alias_or_name.lower()}
        all_aliases = {
            table.alias_or_name.lower() for table in root.find_all(exp.Table)
        }
        rewritten: List[exp.Join] = []
        changed = False

        for join in joins:
            if not isinstance(join.this, exp.Table):
                rewritten.append(join)
                continue
            joined_table = join.this.name.lower()
            joined_alias = join.this.alias_or_name.lower()
            aliases = {**introduced, joined_table: joined_alias}
            on_expression = join.args.get("on")
            references_cte = bool(
                on_expression
                and any(
                    column.table and column.table.lower() in cte_aliases
                    for column in on_expression.find_all(exp.Column)
                )
            )
            if references_cte:
                rewritten.append(join)
                introduced[joined_table] = joined_alias
                continue
            already_valid = bool(
                on_expression
                and any(
                    self._is_foreign_key_equality(equality, aliases)
                    for equality in on_expression.find_all(exp.EQ)
                )
            )
            if already_valid:
                rewritten.append(join)
                introduced[joined_table] = joined_alias
                continue

            direct = self._edges_between(set(introduced), joined_table)
            if len(direct) == 1:
                join.set("on", self._edge_equality(direct[0], aliases))
                changed = True
            elif not direct:
                bridge_paths = self._single_bridge_paths(set(introduced), joined_table)
                if len(bridge_paths) == 1:
                    first_edge, second_edge, bridge = bridge_paths[0]
                    if bridge not in introduced and bridge not in all_aliases:
                        bridge_alias = bridge
                        bridge_aliases = {**introduced, bridge: bridge_alias}
                        rewritten.append(
                            exp.Join(
                                this=exp.to_table(bridge),
                                on=self._edge_equality(first_edge, bridge_aliases),
                            )
                        )
                        introduced[bridge] = bridge_alias
                        aliases = {**introduced, joined_table: joined_alias}
                        join.set("on", self._edge_equality(second_edge, aliases))
                        changed = True
            rewritten.append(join)
            introduced[joined_table] = joined_alias

        if not changed:
            return sql
        root.set("joins", rewritten)
        return root.sql(dialect="postgres")

    def normalize_known_field_aliases(self, sql: str) -> str:
        try:
            root = sqlglot.parse_one(sql, read="postgres")
        except sqlglot.errors.ParseError:
            return sql
        aliases = {
            table.alias_or_name.lower(): table.name.lower()
            for table in root.find_all(exp.Table)
        }
        changed = False
        for column in root.find_all(exp.Column):
            if not column.table:
                continue
            table = aliases.get(column.table.lower(), column.table.lower())
            replacement = self._FIELD_ALIASES.get((table, column.name.lower()))
            if replacement:
                column.set("this", exp.Identifier(this=replacement))
                changed = True
        return root.sql(dialect="postgres") if changed else sql

    @staticmethod
    def _has_status_filter(sql: str, status: str) -> bool:
        return bool(
            re.search(
                rf"\b(?:[a-z_][a-z0-9_]*\.)?status\s*=\s*['\"]{re.escape(status)}['\"]",
                sql,
            )
        )

    def _edges_between(
        self, source_tables: Set[str], target_table: str
    ) -> List[frozenset[Tuple[str, str]]]:
        return [
            edge
            for edge in self.foreign_keys
            if any(table == target_table for table, _ in edge)
            and any(table in source_tables for table, _ in edge)
        ]

    def _single_bridge_paths(
        self, source_tables: Set[str], target_table: str
    ) -> List[
        Tuple[
            frozenset[Tuple[str, str]],
            frozenset[Tuple[str, str]],
            str,
        ]
    ]:
        paths = []
        for first in self.foreign_keys:
            first_tables = {table for table, _ in first}
            sources = first_tables & source_tables
            if len(sources) != 1:
                continue
            bridge_candidates = first_tables - sources
            if len(bridge_candidates) != 1:
                continue
            bridge = next(iter(bridge_candidates))
            for second in self.foreign_keys:
                second_tables = {table for table, _ in second}
                if second != first and second_tables == {bridge, target_table}:
                    paths.append((first, second, bridge))
        return paths

    @staticmethod
    def _edge_equality(
        edge: frozenset[Tuple[str, str]], aliases: Dict[str, str]
    ) -> exp.EQ:
        left, right = sorted(edge)
        return exp.EQ(
            this=exp.column(left[1], table=aliases.get(left[0], left[0])),
            expression=exp.column(right[1], table=aliases.get(right[0], right[0])),
        )

    def _is_foreign_key_equality(
        self,
        equality: exp.EQ,
        aliases: Dict[str, str],
    ) -> bool:
        left = self._qualified_column(equality.this, aliases)
        right = self._qualified_column(equality.expression, aliases)
        return bool(left and right and frozenset({left, right}) in self.foreign_keys)

    @staticmethod
    def _qualified_column(
        expression: exp.Expression,
        aliases: Dict[str, str],
    ) -> Optional[Tuple[str, str]]:
        if not isinstance(expression, exp.Column) or not expression.table:
            return None
        qualifier = expression.table.lower()
        return aliases.get(qualifier, qualifier), expression.name.lower()

