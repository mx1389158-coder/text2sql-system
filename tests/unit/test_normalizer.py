from decimal import Decimal

from packages.execution.normalizer import normalize_rows, result_hash


def test_normalize_rows_is_json_safe():
    rows = normalize_rows(["amount"], [(Decimal("12.50"),)])
    assert rows == [{"amount": 12.5}]


def test_result_hash_ignores_row_order():
    left = result_hash(["id"], [(1,), (2,)])
    right = result_hash(["id"], [(2,), (1,)])
    assert left == right

