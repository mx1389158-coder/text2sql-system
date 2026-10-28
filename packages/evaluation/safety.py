from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from packages.execution.guard import SQLGuard, SQLSafetyError


@dataclass(frozen=True)
class SafetyCase:
    sql: str
    should_allow: bool
    label: str


@dataclass(frozen=True)
class SafetyReport:
    total: int
    correct: int
    true_positive_rate: float
    false_positive_rate: float
    failures: List[str]


def evaluate_safety(guard: SQLGuard, cases: Iterable[SafetyCase]) -> SafetyReport:
    items = list(cases)
    correct = 0
    blocked_attacks = 0
    attacks = 0
    blocked_normal = 0
    normal = 0
    failures = []
    for case in items:
        try:
            guard.validate_and_rewrite(case.sql)
            allowed = True
        except SQLSafetyError:
            allowed = False
        if not case.should_allow:
            attacks += 1
            blocked_attacks += int(not allowed)
        else:
            normal += 1
            blocked_normal += int(not allowed)
        if allowed == case.should_allow:
            correct += 1
        else:
            failures.append(case.label)
    return SafetyReport(
        total=len(items),
        correct=correct,
        true_positive_rate=blocked_attacks / max(1, attacks),
        false_positive_rate=blocked_normal / max(1, normal),
        failures=failures,
    )

