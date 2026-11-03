import json

from packages.execution.access import AccessPolicy
from packages.execution.guard import GuardPolicy, SQLGuard, SQLSafetyError


def test_scope_policy_restricts_columns_and_sample_values(tmp_path):
    path = tmp_path / "access.json"
    path.write_text(
        json.dumps(
            {
                "scopes": {
                    "limited": {
                        "schemas": ["public"],
                        "tables": ["products"],
                        "columns": {"products": ["id", "model_code"]},
                        "sample_values": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    policy = AccessPolicy.from_json(path, {"products", "orders"}, "public").resolve(
        "limited"
    )

    assert policy.tables == {"products"}
    assert policy.allowed_columns("products", {"id", "model_code", "name"}) == {
        "id",
        "model_code",
    }
    assert not policy.allows_sample_value("products", "model_code")


def test_restricted_guard_rejects_star_and_hidden_column():
    guard = SQLGuard(
        GuardPolicy(
            allowed_tables={"products"},
            allowed_columns={"products": {"id", "model_code"}},
            deny_select_star=True,
        )
    )

    for sql in ("SELECT * FROM products", "SELECT name FROM products"):
        try:
            guard.validate_and_rewrite(sql)
        except SQLSafetyError as error:
            assert error.code == "column_denied"
        else:
            raise AssertionError(f"restricted SQL should be rejected: {sql}")

    assert "model_code" in guard.validate_and_rewrite(
        "SELECT model_code FROM products"
    ).sql
