from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

@dataclass(frozen=True)
class SemanticDefinition:
    key: str
    name: str
    definition: str
    version: str
    aliases: List[str]
    ambiguity_question: Optional[str] = None
    options: Optional[List[str]] = None
    retrieval_enabled: bool = True


class SemanticCatalog:
    def __init__(
        self, definitions: List[SemanticDefinition], version: str = "unversioned"
    ):
        self.definitions = definitions
        self.version = version

    @classmethod
    def from_json(cls, path: str | Path) -> "SemanticCatalog":
        raw_bytes = Path(path).read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
        declared_version = str(raw.get("version") or "unversioned")
        content_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]
        return cls(
            [SemanticDefinition(**item) for item in raw["definitions"]],
            version=f"{declared_version}:sha256:{content_hash}",
        )

    def retrieve(self, question: str, limit: int = 4) -> List[SemanticDefinition]:
        normalized_question = question.lower()
        matched = []
        for definition in self.definitions:
            if not definition.retrieval_enabled:
                continue
            aliases = [definition.name, *definition.aliases]
            hits = [alias for alias in aliases if alias.lower() in normalized_question]
            if hits:
                matched.append((max(len(alias) for alias in hits), definition.key, definition))
        matched.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in matched[:limit]]

    def ambiguity(self, question: str) -> Optional[Dict[str, object]]:
        normalized_question = question.lower()
        for definition in self.definitions:
            # Some governed questions already state enough of the disputed
            # definition.  Do not turn those into false-positive blockers.
            if (
                definition.key == "satisfaction"
                and "平均" in normalized_question
                and "评价数" in normalized_question
            ):
                continue
            if definition.key == "inventory_snapshot" and "仓库" in normalized_question:
                continue
            # Clarification is a blocking action, so loose character/n-gram
            # overlap is not enough evidence.  Require a complete business
            # alias to avoid matches such as 设备量 -> 订单量.
            alias_matched = any(
                alias.lower() in normalized_question for alias in definition.aliases
            )
            if definition.ambiguity_question and alias_matched:
                return {
                    "key": definition.key,
                    "question": definition.ambiguity_question,
                    "options": definition.options or [],
                }
        return None

