from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from .models import GeneratedCandidate, GenerationRequest
from .prompts import build_system_prompt, build_user_prompt


class SQLProvider(ABC):
    name = "abstract"

    @abstractmethod
    async def generate(self, request: GenerationRequest, temperature: float = 0.0) -> GeneratedCandidate:
        raise NotImplementedError

    async def generate_many(
        self,
        request: GenerationRequest,
        *,
        temperature: float,
        count: int,
    ) -> List[GeneratedCandidate]:
        return [await self.generate(request, temperature=temperature) for _ in range(count)]


class ProviderGenerationError(ValueError):
    """Generation failed after the provider had already consumed model work."""

    def __init__(
        self,
        message: str,
        *,
        provider_calls: int,
        prompt_tokens: int,
        completion_tokens: int,
    ):
        super().__init__(message)
        self.provider_calls = provider_calls
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class OpenAICompatibleProvider(SQLProvider):
    name = "openai-compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        parse_retries: int = 1,
        max_tokens: int = 256,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.parse_retries = parse_retries
        self.max_tokens = max_tokens

    async def generate(self, request: GenerationRequest, temperature: float = 0.0) -> GeneratedCandidate:
        return (await self.generate_many(request, temperature=temperature, count=1))[0]

    async def generate_many(
        self,
        request: GenerationRequest,
        *,
        temperature: float,
        count: int,
    ) -> List[GeneratedCandidate]:
        import httpx

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": build_user_prompt(request)},
            ],
            "do_sample": temperature > 0,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "n": count,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        usage: Dict[str, Any] = {}
        api_calls = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        raw_responses: List[str] = []
        parsed_responses: List[tuple[str, Dict[str, Any]]] = []
        parse_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for attempt in range(self.parse_retries + 1):
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
                response.raise_for_status()
                api_calls += 1
                response_payload = response.json()
                usage = response_payload.get("usage") or {}
                total_prompt_tokens += int(usage.get("prompt_tokens") or 0)
                total_completion_tokens += int(usage.get("completion_tokens") or 0)
                raw_responses = [
                    str(choice["message"]["content"])
                    for choice in response_payload.get("choices") or []
                ]
                parsed_responses = []
                for raw in raw_responses:
                    try:
                        parsed_responses.append((raw, self._parse_json(raw)))
                    except (json.JSONDecodeError, ValueError) as error:
                        parse_error = error
                if parsed_responses:
                    break
                if attempt >= self.parse_retries:
                    break
                payload["messages"].append(
                    {"role": "assistant", "content": raw_responses[0] if raw_responses else ""}
                )
                payload["messages"].append(
                    {
                        "role": "user",
                        "content": "上一个响应不是合法 JSON。只返回符合约定字段的 JSON object。",
                    }
                )
        if not parsed_responses:
            raise ProviderGenerationError(
                str(parse_error or "模型未返回可解析的 JSON object"),
                provider_calls=api_calls,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
            )
        candidates = []
        for index, (raw, parsed) in enumerate(parsed_responses):
            candidates.append(
                GeneratedCandidate(
                    sql=str(parsed.get("sql", "")).strip(),
                    intent=str(parsed.get("intent", "QUERY")).upper(),
                    used_tables=list(parsed.get("used_tables") or []),
                    assumptions=list(parsed.get("assumptions") or []),
                    raw_response=raw,
                    temperature=temperature,
                    provider=self.name,
                    prompt_tokens=total_prompt_tokens if index == 0 else 0,
                    completion_tokens=total_completion_tokens if index == 0 else 0,
                    provider_calls=api_calls if index == 0 else 0,
                )
            )
        return candidates

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        value = raw.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE)
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            # A fixed generation budget can truncate optional fields after a
            # complete SQL value. Recover only that fully closed JSON string;
            # an incomplete SQL string is still rejected. SQLGuard remains the
            # authority for syntax, schema and read-only safety.
            sql_key = re.search(r'"sql"\s*:\s*', value)
            if sql_key is None:
                raise
            try:
                sql, _ = json.JSONDecoder().raw_decode(value, sql_key.end())
            except json.JSONDecodeError:
                raise error from None
            if not isinstance(sql, str) or not sql.strip():
                raise error from None
            return {
                "intent": "QUERY",
                "sql": sql,
                "used_tables": [],
                "assumptions": ["model response truncated after a complete SQL field"],
            }
        if not isinstance(parsed, dict):
            raise ValueError("模型结构化输出必须是 JSON object")
        return parsed


class DemoSQLProvider(SQLProvider):
    """Offline provider for the demo and tests; production should use a real model endpoint."""

    name = "demo-rules"

    async def generate(self, request: GenerationRequest, temperature: float = 0.0) -> GeneratedCandidate:
        question = request.question
        sql: str
        tables: List[str]
        assumptions: List[str] = ["离线演示规则生成；生产环境请连接本地模型"]

        if "重复报修" in question or "再次报修" in question:
            sql = """WITH ordered_tickets AS (
  SELECT t.id, t.device_id, t.fault_code_id, t.created_at,
         LAG(t.created_at) OVER (PARTITION BY t.device_id ORDER BY t.created_at) AS previous_at
  FROM tickets AS t
  WHERE t.status <> 'cancelled'
)
SELECT p.model_code, f.category AS fault_category, COUNT(*) AS repeat_ticket_count
FROM ordered_tickets AS ot
JOIN devices AS d ON d.id = ot.device_id
JOIN products AS p ON p.id = d.product_id
LEFT JOIN fault_codes AS f ON f.id = ot.fault_code_id
WHERE ot.previous_at IS NOT NULL
  AND ot.created_at <= ot.previous_at + INTERVAL '7 days'
GROUP BY p.model_code, f.category
ORDER BY repeat_ticket_count DESC
LIMIT 200"""
            tables = ["tickets", "devices", "products", "fault_codes"]
        elif "处理时长" in question or "解决时长" in question:
            sql = """SELECT p.model_code,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.resolved_at - t.created_at)) / 3600.0), 2) AS avg_resolution_hours,
       COUNT(*) AS ticket_count
FROM tickets AS t
JOIN devices AS d ON d.id = t.device_id
JOIN products AS p ON p.id = d.product_id
WHERE t.status = 'resolved' AND t.resolved_at IS NOT NULL
GROUP BY p.model_code
ORDER BY avg_resolution_hours
LIMIT 200"""
            tables = ["tickets", "devices", "products"]
        elif "满意度" in question or "评分" in question:
            sql = """SELECT p.model_code, ROUND(AVG(s.score), 2) AS avg_score, COUNT(*) AS survey_count
FROM satisfaction_surveys AS s
JOIN tickets AS t ON t.id = s.ticket_id
JOIN devices AS d ON d.id = t.device_id
JOIN products AS p ON p.id = d.product_id
GROUP BY p.model_code
ORDER BY avg_score DESC
LIMIT 200"""
            tables = ["satisfaction_surveys", "tickets", "devices", "products"]
        elif "退换货" in question or "退货率" in question:
            sql = """SELECT p.model_code,
       ROUND(100.0 * COUNT(DISTINCT CASE WHEN r.status = 'approved' AND r.refund_type IN ('return', 'exchange') THEN oi.id END)
             / NULLIF(COUNT(DISTINCT oi.id), 0), 2) AS return_exchange_rate_pct
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
LEFT JOIN refunds AS r ON r.order_item_id = oi.id
WHERE o.status IN ('paid', 'completed')
GROUP BY p.model_code
ORDER BY return_exchange_rate_pct DESC
LIMIT 200"""
            tables = ["order_items", "orders", "products", "refunds"]
        elif "订单" in question and any(word in question for word in ["数量", "多少", "总数"]):
            sql = "SELECT COUNT(*) AS order_count FROM orders WHERE status IN ('paid', 'completed')"
            tables = ["orders"]
        elif "产品" in question or "型号" in question:
            sql = "SELECT model_code, name, list_price FROM products ORDER BY model_code LIMIT 200"
            tables = ["products"]
        else:
            first_table = self._first_table(request.mschema)
            sql = f'SELECT * FROM "{first_table}" LIMIT 50'
            tables = [first_table]
            assumptions.append("未匹配演示模板，返回最相关表的样例行")
        return GeneratedCandidate(
            sql=sql,
            used_tables=tables,
            assumptions=assumptions,
            raw_response=json.dumps(
                {"intent": "QUERY", "sql": sql, "used_tables": tables, "assumptions": assumptions},
                ensure_ascii=False,
            ),
            temperature=temperature,
            provider=self.name,
            prompt_tokens=max(1, len(build_user_prompt(request)) // 4),
            completion_tokens=max(1, len(sql) // 4),
        )

    @staticmethod
    def _first_table(mschema: str) -> str:
        match = re.search(r"^# Table:\s*([a-zA-Z_][a-zA-Z0-9_]*)", mschema, re.MULTILINE)
        return match.group(1) if match else "products"

