from packages.evaluation.metrics import column_recall, result_hash, result_value_hash


def test_column_recall_is_case_insensitive():
    assert column_recall(["Orders.ID", "orders.status"], ["orders.id"]) == 1.0


def test_result_hash_is_order_insensitive_by_default():
    left = [{"id": 1}, {"id": 2}]
    right = list(reversed(left))
    assert result_hash(left) == result_hash(right)
    assert result_hash(left, order_sensitive=True) != result_hash(right, order_sensitive=True)


def test_result_value_hash_ignores_output_aliases_but_preserves_value_order():
    expected = [{"firmware_count": 2, "model": "LOCK-X1"}]
    renamed = [{"version_count": 2, "product_model": "LOCK-X1"}]
    reordered = [{"product_model": "LOCK-X1", "version_count": 2}]
    assert result_value_hash(expected) == result_value_hash(renamed)
    assert result_value_hash(expected) != result_value_hash(reordered)
