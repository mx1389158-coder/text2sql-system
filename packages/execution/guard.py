from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set

import sqlglot
from sqlglot import exp


class SQLSafetyError(ValueError):
    def __init__(self, reason: str, code: str = "unsafe_sql"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class GuardPolicy:
    max_rows: int = 200
    allowed_tables: Set[str] = field(default_factory=set)
    allowed_functions: Set[str] = field(
        default_factory=lambda: {
            "abs", "avg", "coalesce", "concat", "count", "current_date", "date",
            "date_part", "date_trunc", "dense_rank", "extract", "greatest", "lag",
            "lead", "least", "lower", "max", "min", "nullif", "rank", "replace",
            "round", "row_number", "substring", "sum", "to_char", "trim", "upper",
        }
    )
    denied_functions: Set[str] = field(
        default_factory=lambda: {
            "dblink", "dblink_connect", "lo_export", "lo_import", "pg_read_file",
            "pg_read_binary_file", "pg_sleep", "pg_terminate_backend", "set_config",
        }
    )
    denied_schemas: Set[str] = field(
        default_factory=lambda: {"information_schema", "pg_catalog", "pg_toast"}
    )
    allowed_schemas: Set[str] = field(default_factory=set)


@dataclass(frozen=True)
class GuardResult:
    sql: str
    referenced_tables: List[str]
    applied_limit: int


class SQLGuard:
    _forbidden_text = re.compile(
        r"\b(copy|call|do|vacuum|analyze|listen|notify|unlisten|set|reset|show)\b",
        re.IGNORECASE,
    )

    def __init__(self, policy: GuardPolicy):
        self.policy = policy

    def validate_and_rewrite(self, sql: str) -> GuardResult:
        if not sql or len(sql) > 50_000:
            raise SQLSafetyError("SQL 为空或长度超限", "invalid_length")
        if self._forbidden_text.search(self._strip_literals(sql)):
            raise SQLSafetyError("包含不允许的数据库命令", "forbidden_command")
        try:
            statements = sqlglot.parse(sql, read="postgres")
        except sqlglot.errors.ParseError as error:
            raise SQLSafetyError(f"SQL 无法解析：{error}", "parse_error") from error
        statements = [statement for statement in statements if statement is not None]
        if len(statements) != 1:
            raise SQLSafetyError("只允许单条 SQL", "multiple_statements")
        root = statements[0]
        if not isinstance(root, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            raise SQLSafetyError("只允许 SELECT/WITH 查询", "not_read_only")

        forbidden_nodes = (
            exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter,
            exp.Command, exp.Merge, exp.Transaction, exp.Grant, exp.Revoke,
        )
        for node_type in forbidden_nodes:
            if root.find(node_type):
                raise SQLSafetyError("查询包含写入或管理操作", "not_read_only")
        if root.find(exp.Lock):
            raise SQLSafetyError("不允许行锁或表锁", "locking_query")

        cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
        referenced: Set[str] = set()
        for table in root.find_all(exp.Table):
            name = table.name.lower()
            schema = (table.db or "").lower()
            if name in cte_names:
                continue
            if schema in self.policy.denied_schemas:
                raise SQLSafetyError(f"不允许访问系统 Schema：{schema}", "system_schema")
            if schema and self.policy.allowed_schemas and schema not in {
                item.lower() for item in self.policy.allowed_schemas
            }:
                raise SQLSafetyError(f"不允许访问 Schema：{schema}", "schema_denied")
            referenced.add(name)
        if self.policy.allowed_tables:
            unknown = referenced - {name.lower() for name in self.policy.allowed_tables}
            if unknown:
                raise SQLSafetyError(f"访问未授权表：{', '.join(sorted(unknown))}", "table_denied")

        for function in root.find_all(exp.Func):
            name = self._function_name(function)
            if name in self.policy.denied_functions:
                raise SQLSafetyError(f"危险函数被拒绝：{name}", "function_denied")
            if isinstance(function, exp.Anonymous) and name not in self.policy.allowed_functions:
                raise SQLSafetyError(f"函数不在白名单：{name}", "function_denied")

        applied_limit = self.policy.max_rows
        current_limit = root.args.get("limit")
        if current_limit is not None:
            try:
                requested = int(current_limit.expression.name)
                applied_limit = min(requested, self.policy.max_rows)
            except (AttributeError, TypeError, ValueError):
                applied_limit = self.policy.max_rows
        root.set("limit", exp.Limit(expression=exp.Literal.number(applied_limit)))
        return GuardResult(
            sql=root.sql(dialect="postgres"),
            referenced_tables=sorted(referenced),
            applied_limit=applied_limit,
        )

    @staticmethod
    def _function_name(function: exp.Func) -> str:
        if isinstance(function, exp.Anonymous):
            return function.name.lower()
        try:
            return function.sql_name().lower()
        except Exception:
            return function.key.lower()

    @staticmethod
    def _strip_literals(sql: str) -> str:
        return re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"", "", sql)

