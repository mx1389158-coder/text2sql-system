from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .retriever import tokenize


@dataclass(frozen=True)
class SemanticDefinition:
    key: str
    name: str
    definition: str
    version: str
    aliases: List[str]
    ambiguity_question: Optional[str] = None
    options: Optional[List[str]] = None


class SemanticCatalog:
    def __init__(self, definitions: List[SemanticDefinition]):
        self.definitions = definitions

    @classmethod
    def from_json(cls, path: str | Path) -> "SemanticCatalog":
        with Path(path).open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return cls([SemanticDefinition(**item) for item in raw["definitions"]])

    def retrieve(self, question: str, limit: int = 4) -> List[SemanticDefinition]:
        question_terms = set(tokenize(question))
        scored = []
        for definition in self.definitions:
            terms = set(tokenize(" ".join([definition.name, *definition.aliases])))
            score = len(question_terms & terms)
            if any(alias.lower() in question.lower() for alias in definition.aliases):
                score += 3
            if score:
                scored.append((score, definition.key, definition))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored[:limit]]

    def ambiguity(self, question: str) -> Optional[Dict[str, object]]:
        for definition in self.retrieve(question):
            if definition.ambiguity_question:
                return {
                    "key": definition.key,
                    "question": definition.ambiguity_question,
                    "options": definition.options or [],
                }
        return None

