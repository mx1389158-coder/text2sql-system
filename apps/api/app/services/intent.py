from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas.query import Intent


@dataclass(frozen=True)
class IntentDecision:
    intent: Intent
    reason: str = ""


class IntentClassifier:
    _injection = re.compile(
        r"忽略.{0,8}(规则|指令|提示)|system prompt|系统提示词|绕过.{0,8}(安全|权限)",
        re.IGNORECASE,
    )
    _write_request = re.compile(
        r"(?:^|\s|请|帮我)(delete|update|insert|drop|truncate|alter|create|grant|revoke|copy)\b|"
        r"(删除|修改|写入|插入|清空|创建).{0,8}(表|数据|记录|权限)",
        re.IGNORECASE,
    )
    _meta = re.compile(r"有哪些表|什么表|字段|表结构|schema|数据库结构", re.IGNORECASE)

    def classify(self, question: str) -> IntentDecision:
        if self._injection.search(question):
            return IntentDecision(Intent.REJECT, "检测到提示注入或绕过安全规则的请求")
        if self._write_request.search(question):
            return IntentDecision(Intent.REJECT, "系统只允许只读分析，不执行写入或权限操作")
        if self._meta.search(question):
            return IntentDecision(Intent.META, "数据库目录查询")
        return IntentDecision(Intent.QUERY)

