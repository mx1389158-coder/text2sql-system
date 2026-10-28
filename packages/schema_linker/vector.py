from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, List


_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*|[\u4e00-\u9fff]")


class HashingTextEncoder:
    """Dependency-free dense encoder used when no external embedding service is configured.

    It is intentionally deterministic so evaluation runs remain reproducible.  A production
    deployment can replace it with a sentence-transformer without changing the retriever API.
    """

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def encode(self, text: str) -> List[float]:
        normalized = text.lower().replace("_", " ")
        tokens = _TOKEN_RE.findall(normalized)
        chinese = "".join(token for token in tokens if "\u4e00" <= token <= "\u9fff")
        features: Iterable[str] = [
            *tokens,
            *(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))),
            *(chinese[index : index + 3] for index in range(max(0, len(chinese) - 2))),
        ]
        vector = [0.0] * self.dimensions
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "big") % self.dimensions
            sign = 1.0 if digest[0] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return vector if norm == 0 else [value / norm for value in vector]

    @staticmethod
    def cosine(left: List[float], right: List[float]) -> float:
        return sum(a * b for a, b in zip(left, right, strict=False))
