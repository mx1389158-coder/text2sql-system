import pytest

from packages.execution.guard import SQLSafetyError


def test_select_is_limited(guard):
    result = guard.validate_and_rewrite("SELECT id, model_code FROM products")
    assert "LIMIT 200" in result.sql
    assert result.referenced_tables == ["products"]


def test_existing_limit_is_capped(guard):
    result = guard.validate_and_rewrite("SELECT id FROM products LIMIT 9999")
    assert "LIMIT 200" in result.sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "SELECT 1; DROP TABLE orders",
        "SELECT pg_sleep(10)",
        "SELECT * FROM pg_catalog.pg_user",
        "SELECT * FROM secret_table",
        "SELECT * FROM orders FOR UPDATE",
        "WITH changed AS (DELETE FROM orders RETURNING id) SELECT id FROM changed",
        "WITH changed AS (UPDATE orders SET status='paid' RETURNING id) SELECT id FROM changed",
    ],
)
def test_dangerous_sql_is_rejected(guard, sql):
    with pytest.raises(SQLSafetyError):
        guard.validate_and_rewrite(sql)


def test_cte_alias_is_not_treated_as_table(guard):
    result = guard.validate_and_rewrite(
        "WITH recent AS (SELECT id FROM orders) SELECT COUNT(*) FROM recent"
    )
    assert result.referenced_tables == ["orders"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT p.not_a_column FROM products AS p",
        "SELECT not_a_column FROM products",
        "SELECT fw.model_code FROM firmware_versions AS fw",
    ],
)
def test_unknown_columns_are_rejected_before_execution(guard, sql):
    with pytest.raises(SQLSafetyError) as error:
        guard.validate_and_rewrite(sql)
    assert error.value.code == "column_denied"


def test_output_alias_is_allowed_in_order_by(guard):
    result = guard.validate_and_rewrite(
        "SELECT COUNT(*) AS order_count FROM orders ORDER BY order_count DESC"
    )
    assert "ORDER BY order_count DESC" in result.sql

