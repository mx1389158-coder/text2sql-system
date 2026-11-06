from __future__ import annotations

import json

from scripts.ensure_evaluation_auth import ensure_evaluation_scope


def _read(path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def test_single_key_is_preserved_as_default_and_evaluation_key_is_added(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "TEXT2SQL_ENV=production\nTEXT2SQL_API_KEY=existing-key\n"
        "TEXT2SQL_API_KEYS_JSON=\nOTHER=value\n",
        encoding="utf-8",
    )

    assert ensure_evaluation_scope(path) is True

    values = _read(path)
    scoped = json.loads(values["TEXT2SQL_API_KEYS_JSON"])
    assert values["TEXT2SQL_API_KEY"] == ""
    assert scoped["existing-key"] == "default"
    assert list(scoped.values()).count("evaluation") == 1
    assert values["OTHER"] == "value"


def test_existing_evaluation_scope_is_not_rewritten(tmp_path):
    path = tmp_path / ".env"
    original = 'TEXT2SQL_API_KEY=\nTEXT2SQL_API_KEYS_JSON={"eval-key":"evaluation"}\n'
    path.write_text(original, encoding="utf-8")

    assert ensure_evaluation_scope(path) is False
    assert path.read_text(encoding="utf-8") == original
