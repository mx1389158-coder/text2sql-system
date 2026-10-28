from __future__ import annotations

import math
import re
from collections import Counter, defaultdict, deque
from typing import Dict, List, Set, Tuple

from .models import ColumnEvidence, DatabaseCatalog, SchemaEvidence, TableInfo
from .vector import HashingTextEncoder


TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*|[\u4e00-\u9fff]")


def tokenize(text: str) -> List[str]:
    normalized = text.lower().replace("_", " ")
    raw = TOKEN_RE.findall(normalized)
    chinese = "".join(token for token in raw if "\u4e00" <= token <= "\u9fff")
    grams = [chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))]
    return raw + grams


class SchemaRetriever:
    def __init__(self, catalog: DatabaseCatalog, dense_weight: float = 0.35):
        self.catalog = catalog
        self.dense_weight = max(0.0, min(1.0, dense_weight))
        self.encoder = HashingTextEncoder()
        self._documents: Dict[str, Counter[str]] = {}
        self._vectors: Dict[str, List[float]] = {}
        self._idf: Dict[str, float] = {}
        self._graph: Dict[str, Set[str]] = defaultdict(set)
        self._build_index()

    def _build_index(self) -> None:
        document_frequency: Counter[str] = Counter()
        for table in self.catalog.tables:
            text_parts = [table.name, table.description, *table.aliases]
            for column in table.columns:
                text_parts.extend([column.name, column.description, *column.aliases])
                text_parts.extend(str(value) for value in column.examples)
            terms = Counter(tokenize(" ".join(text_parts)))
            self._documents[table.name] = terms
            self._vectors[table.name] = self.encoder.encode(" ".join(text_parts))
            document_frequency.update(set(terms))
            for foreign_key in table.foreign_keys:
                self._graph[table.name].add(foreign_key.referred_table)
                self._graph[foreign_key.referred_table].add(table.name)
        count = max(1, len(self._documents))
        self._idf = {
            term: math.log((count + 1) / (frequency + 1)) + 1
            for term, frequency in document_frequency.items()
        }

    def retrieve(
        self,
        question: str,
        top_k: int = 6,
        expand_join_paths: bool = True,
        expand_if_low_confidence: bool = True,
        max_top_k: int = 12,
    ) -> SchemaEvidence:
        query_terms = Counter(tokenize(question))
        query_vector = self.encoder.encode(question)
        scores: Dict[str, float] = {}
        for table_name, terms in self._documents.items():
            lexical = sum(
                min(query_count, terms.get(term, 0)) * self._idf.get(term, 1.0)
                for term, query_count in query_terms.items()
            )
            table = self.catalog.table_map[table_name]
            if table.name.lower() in question.lower():
                lexical += 5.0
            dense = max(0.0, self.encoder.cosine(query_vector, self._vectors[table_name]))
            scores[table_name] = lexical * (1.0 - self.dense_weight) + dense * self.dense_weight

        ranked = sorted(scores, key=lambda name: (-scores[name], name))
        confidence = self._confidence(ranked, scores)
        effective_top_k = top_k
        expanded = False
        if expand_if_low_confidence and confidence < 0.35:
            effective_top_k = min(max_top_k, max(top_k + 2, top_k * 2))
            expanded = effective_top_k > top_k
        selected = [name for name in ranked if scores[name] > 0][:effective_top_k]
        if not selected:
            selected = ranked[: min(effective_top_k, len(ranked))]

        path_tables: List[str] = []
        if expand_join_paths and len(selected) > 1:
            selected_set = set(selected)
            for index, left in enumerate(selected):
                for right in selected[index + 1 :]:
                    for node in self._shortest_path(left, right):
                        if node not in selected_set:
                            selected_set.add(node)
                            path_tables.append(node)
            selected.extend(path_tables)

        columns: List[ColumnEvidence] = []
        for table_name in selected:
            table = self.catalog.table_map[table_name]
            columns.extend(self._rank_columns(table, query_terms))
        return SchemaEvidence(
            selected_tables=selected,
            table_scores={name: round(scores[name], 4) for name in selected},
            selected_columns=columns,
            join_path_tables=path_tables,
            expanded=expanded,
            confidence=round(confidence, 4),
        )

    @staticmethod
    def _confidence(ranked: List[str], scores: Dict[str, float]) -> float:
        if not ranked or scores[ranked[0]] <= 0:
            return 0.0
        first = scores[ranked[0]]
        second = scores[ranked[1]] if len(ranked) > 1 else 0.0
        separation = max(0.0, (first - second) / max(first, 1e-9))
        strength = 1.0 - math.exp(-first / 2.0)
        return min(1.0, 0.65 * strength + 0.35 * separation)

    def _rank_columns(
        self, table: TableInfo, query_terms: Counter[str], per_table: int = 12
    ) -> List[ColumnEvidence]:
        ranked: List[Tuple[float, str]] = []
        for column in table.columns:
            terms = Counter(
                tokenize(
                    " ".join(
                        [column.name, column.description, *column.aliases]
                        + [str(value) for value in column.examples]
                    )
                )
            )
            score = sum(
                min(count, terms.get(term, 0)) * self._idf.get(term, 1.0)
                for term, count in query_terms.items()
            )
            if column.primary_key:
                score += 0.05
            ranked.append((score, column.name))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        chosen = ranked[:per_table]
        return [ColumnEvidence(table.name, name, round(score, 4)) for score, name in chosen]

    def _shortest_path(self, start: str, end: str) -> List[str]:
        queue = deque([(start, [start])])
        visited = {start}
        while queue:
            node, path = queue.popleft()
            if node == end:
                return path
            for neighbor in sorted(self._graph.get(node, set())):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return []

