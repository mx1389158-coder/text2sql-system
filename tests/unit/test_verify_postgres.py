from scripts.verify_postgres import load_env, urls_from_env


def test_database_urls_are_built_from_env_without_logging_secrets(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_ADMIN_PASSWORD=admin p@ss\n"
        "TEXT2SQL_READONLY_PASSWORD=read/on?ly\n",
        encoding="utf-8",
    )

    values = load_env(env_file)
    admin_url, readonly_url = urls_from_env(env_file, "127.0.0.1", 15432)

    assert values["POSTGRES_ADMIN_PASSWORD"] == "admin p@ss"
    assert "admin%20p%40ss" in admin_url
    assert "read%2Fon%3Fly" in readonly_url
