from scripts.ensure_api_auth import ensure_api_auth


def test_ensure_api_auth_generates_key_without_printing_or_overwriting(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "TEXT2SQL_ENV=production\nTEXT2SQL_API_KEY=\nKEEP_ME=value\n",
        encoding="utf-8",
    )

    assert ensure_api_auth(path) is True
    content = path.read_text(encoding="utf-8")
    assert "TEXT2SQL_API_KEY=" in content
    assert "TEXT2SQL_API_KEY=\n" not in content
    assert "KEEP_ME=value" in content
    first_content = content

    assert ensure_api_auth(path) is False
    assert path.read_text(encoding="utf-8") == first_content


def test_ensure_api_auth_preserves_existing_multi_key_configuration(tmp_path):
    path = tmp_path / ".env"
    content = 'TEXT2SQL_API_KEY=\nTEXT2SQL_API_KEYS_JSON={"key":"default"}\n'
    path.write_text(content, encoding="utf-8")

    assert ensure_api_auth(path) is False
    assert path.read_text(encoding="utf-8") == content
