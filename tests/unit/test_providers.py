import json

import pytest

from packages.generation.providers import OpenAICompatibleProvider


def test_parse_json_recovers_complete_sql_from_truncated_optional_field():
    raw = (
        '{"intent":"QUERY","sql":"SELECT COUNT(*) FROM orders LIMIT 200",'
        '"used_tables":["orders"],"assumptions":["truncated'
    )

    parsed = OpenAICompatibleProvider._parse_json(raw)

    assert parsed["sql"] == "SELECT COUNT(*) FROM orders LIMIT 200"
    assert parsed["used_tables"] == []


def test_parse_json_does_not_recover_an_unterminated_sql_string():
    raw = '{"intent":"QUERY","sql":"SELECT * FROM orders'

    with pytest.raises(json.JSONDecodeError):
        OpenAICompatibleProvider._parse_json(raw)
