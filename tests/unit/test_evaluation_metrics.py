from packages.evaluation.metrics import column_recall, result_hash


def test_column_recall_is_case_insensitive():
    assert column_recall(["Orders.ID", "orders.status"], ["orders.id"]) == 1.0


def test_result_hash_is_order_insensitive_by_default():
    left = [{"id": 1}, {"id": 2}]
    right = list(reversed(left))
    assert result_hash(left) == result_hash(right)
    assert result_hash(left, order_sensitive=True) != result_hash(right, order_sensitive=True)
