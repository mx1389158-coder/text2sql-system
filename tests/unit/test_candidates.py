from __future__ import annotations

import asyncio

from packages.generation.candidates import (
    CandidateGenerator,
    CandidateSelector,
    LightweightCandidateScorer,
)
from packages.generation.models import CandidateScore, GeneratedCandidate, GenerationRequest
from packages.generation.providers import SQLProvider


class RecordingProvider(SQLProvider):
    def __init__(self) -> None:
        self.single_temperatures: list[float] = []
        self.batch_calls: list[tuple[float, int]] = []

    async def generate(
        self, request: GenerationRequest, temperature: float = 0.0
    ) -> GeneratedCandidate:
        self.single_temperatures.append(temperature)
        return GeneratedCandidate(sql="SELECT 1", temperature=temperature)

    async def generate_many(
        self,
        request: GenerationRequest,
        *,
        temperature: float,
        count: int,
    ) -> list[GeneratedCandidate]:
        self.batch_calls.append((temperature, count))
        return [
            GeneratedCandidate(sql=f"SELECT {index + 2}", temperature=temperature)
            for index in range(count)
        ]


def test_three_candidates_use_one_greedy_and_one_sampled_batch() -> None:
    provider = RecordingProvider()
    request = GenerationRequest(question="测试", mschema="# Table: products")

    candidates = asyncio.run(CandidateGenerator(provider).generate(request, count=3))

    assert [item.sql for item in candidates] == ["SELECT 1", "SELECT 2", "SELECT 3"]
    assert provider.single_temperatures == [0.0]
    assert provider.batch_calls == [(0.2, 2)]


def test_selector_prefers_semantic_alignment_over_non_empty_result() -> None:
    aligned = CandidateScore(
        candidate=GeneratedCandidate(sql="SELECT model_code FROM products"),
        static_valid=True,
        executed=True,
        non_empty=False,
        schema_coverage=1.0,
        semantic_score=0.9,
    )
    unrelated = CandidateScore(
        candidate=GeneratedCandidate(sql="SELECT name FROM teams"),
        static_valid=True,
        executed=True,
        non_empty=True,
        schema_coverage=1.0,
        semantic_score=0.2,
    )
    assert CandidateSelector.choose([unrelated, aligned]) is aligned


def test_semantic_scorer_rewards_question_markers(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    question = "统计2026-01-01以来各团队上门服务次数"
    aligned = GeneratedCandidate(
        sql="SELECT teams.name FROM service_visits JOIN teams ON true "
        "WHERE started_at >= '2026-01-01'"
    )
    unrelated = GeneratedCandidate(sql="SELECT model_code FROM products")
    assert scorer.score(question, aligned) > scorer.score(question, unrelated)


def test_semantic_scorer_penalizes_invalid_join_path(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    question = "统计各团队上门服务次数"
    correct = GeneratedCandidate(
        sql="SELECT tm.name, COUNT(*) FROM service_visits sv "
        "JOIN agents a ON a.id = sv.agent_id "
        "JOIN teams tm ON tm.id = a.team_id GROUP BY tm.name"
    )
    wrong = GeneratedCandidate(
        sql="SELECT tm.name, COUNT(*) FROM service_visits sv "
        "JOIN teams tm ON tm.id = sv.agent_id GROUP BY tm.name"
    )
    assert scorer.score(question, correct) > scorer.score(question, wrong)
    assert scorer.score(question, wrong) < 0.65
    feedback = scorer.feedback(question, wrong)
    assert "service_visits.agent_id" in feedback
    assert "agents.id" in feedback


def test_semantic_scorer_requires_explicit_business_status(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    question = "汇总各产品分类获批的退款金额"
    missing_status = GeneratedCandidate(
        sql="SELECT pc.name, SUM(r.amount) FROM refunds r "
        "JOIN order_items oi ON oi.id=r.order_item_id "
        "JOIN products p ON p.id=oi.product_id "
        "JOIN product_categories pc ON pc.id=p.category_id GROUP BY pc.name"
    )
    approved = GeneratedCandidate(
        sql=missing_status.sql.replace(" GROUP BY", " WHERE r.status='approved' GROUP BY")
    )

    assert scorer.score(question, approved) >= 0.65
    assert scorer.score(question, missing_status) < 0.65
    assert scorer.score(question, missing_status) < scorer.score(question, approved)
    assert "状态筛选(approved)" in scorer.feedback(question, missing_status)


def test_semantic_scorer_normalizes_unique_fk_join_and_bridge(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    sql = (
        "SELECT pc.name, SUM(r.amount) FROM refunds r "
        "JOIN products p ON p.id=r.order_item_product_id "
        "JOIN product_categories pc ON pc.id=p.category_id GROUP BY pc.name"
    )

    normalized = scorer.normalize_unique_fk_joins(sql)

    assert "JOIN order_items" in normalized
    assert "r.order_item_id" in normalized
    assert "order_items.id" in normalized
    assert "order_items.product_id" in normalized
    assert "p.id" in normalized
    assert scorer._join_alignment(normalized) == 1.0


def test_semantic_scorer_does_not_guess_ambiguous_fk_join(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    sql = (
        "SELECT COUNT(*) FROM device_upgrades du "
        "JOIN firmware_versions f ON f.id=du.device_id"
    )

    assert scorer.normalize_unique_fk_joins(sql) == sql


def test_semantic_scorer_normalizes_reviewed_refund_field_aliases(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    sql = (
        "SELECT SUM(r.amount) FROM refunds r "
        "WHERE r.refund_status='approved' AND r.refunded_at >= '2026-01-01'"
    )

    normalized = scorer.normalize_known_field_aliases(sql)

    assert "r.status = 'approved'" in normalized
    assert "r.created_at >= '2026-01-01'" in normalized


def test_semantic_scorer_does_not_treat_refund_type_as_status(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    candidate = GeneratedCandidate(
        sql="SELECT SUM(amount) FROM refunds WHERE refund_type='approved'"
    )

    assert scorer.score("汇总获批的退款金额", candidate) < 0.65


def test_semantic_scorer_explains_missing_business_entity_and_time_direction(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    candidate = GeneratedCandidate(
        sql="SELECT p.model_code FROM devices d JOIN products p ON p.id=d.product_id "
        "WHERE d.activated_at >= '2026-01-01'"
    )
    feedback = scorer.feedback("统计截至2026-01-01各型号到期保修设备数", candidate)
    assert "保修" in feedback
    assert "截止时间方向(<=)" in feedback


def test_semantic_scorer_does_not_penalize_unknown_business_phrase(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    candidate = GeneratedCandidate(sql="SELECT COUNT(*) FROM devices")

    assert scorer.score("统计处于观察状态的设备数量", candidate) >= 0.8


def test_semantic_scorer_recognizes_holdout_business_markers(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    aligned = GeneratedCandidate(
        sql="SELECT pc.name, COUNT(*) FROM device_upgrades du "
        "JOIN devices d ON d.id = du.device_id "
        "JOIN products p ON p.id = d.product_id "
        "JOIN product_categories pc ON pc.id = p.category_id "
        "WHERE du.upgraded_at >= '2026-01-01' GROUP BY pc.name"
    )
    unrelated = GeneratedCandidate(sql="SELECT COUNT(*) FROM tickets")

    assert scorer.score("统计2026-01-01以来各品类设备升级数", aligned) > scorer.score(
        "统计2026-01-01以来各品类设备升级数", unrelated
    )


def test_semantic_scorer_requires_delivery_address_region_path(catalog) -> None:
    scorer = LightweightCandidateScorer(catalog)
    question = "统计2026-01-01以来各地区已送达的订单数"
    delivery_region = GeneratedCandidate(
        sql="SELECT r.name, COUNT(*) FROM shipments s "
        "JOIN customer_addresses ca ON ca.id=s.address_id "
        "JOIN regions r ON r.id=ca.region_id "
        "WHERE s.delivered_at >= '2026-01-01' AND s.status='delivered' GROUP BY r.name"
    )
    customer_region = GeneratedCandidate(
        sql="SELECT r.name, COUNT(*) FROM shipments s "
        "JOIN orders o ON o.id=s.order_id "
        "JOIN customers c ON c.id=o.customer_id "
        "JOIN regions r ON r.id=c.region_id "
        "WHERE s.delivered_at >= '2026-01-01' AND s.status='delivered' GROUP BY r.name"
    )

    assert scorer.score(question, delivery_region) >= 0.65
    assert scorer.score(question, customer_region) < 0.65
    assert "配送地区路径" in scorer.feedback(question, customer_region)
