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

    for sql in (
        "SELECT * FROM products",
        "SELECT p.* FROM products AS p",
        "SELECT name FROM products",
    ):
        try:
            guard.validate_and_rewrite(sql)
        except SQLSafetyError as error:
            assert error.code == "column_denied"
        else:
            raise AssertionError(f"restricted SQL should be rejected: {sql}")

    assert "model_code" in guard.validate_and_rewrite(
        "SELECT model_code FROM products"
    ).sql

    count_result = guard.validate_and_rewrite("SELECT COUNT(*) FROM products")
    assert "COUNT(*)" in count_result.sql


def test_missing_access_policy_fails_closed(tmp_path):
    policy = AccessPolicy.from_json(
        tmp_path / "missing.json", {"products", "orders"}, "public"
    )

    resolved = policy.resolve("default")

    assert policy.version == "missing-deny-all"
    assert resolved.tables == set()
    assert resolved.schemas == set()


def test_unknown_scope_does_not_inherit_default_permissions(tmp_path):
    path = tmp_path / "access.json"
    path.write_text(
        json.dumps(
            {
                "version": "test",
                "scopes": {
                    "default": {
                        "schemas": ["public"],
                        "tables": ["*"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    policy = AccessPolicy.from_json(path, {"products", "orders"}, "public")

    assert policy.resolve("unknown").tables == set()
    assert policy.resolve("unknown").schemas == set()
