import json
from pathlib import Path

import pytest

from apps.api.app.core.config import Settings


def test_langfuse_official_env_names_are_supported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.langfuse.test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    settings = Settings.from_environment()

    assert settings.langfuse_host == "https://example.langfuse.test"
    assert settings.langfuse_public_key == "pk-lf-test"
    assert settings.langfuse_secret_key == "sk-lf-test"


def test_project_langfuse_env_names_take_precedence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://official.example")
    monkeypatch.setenv("TEXT2SQL_LANGFUSE_HOST", "https://project.example")

    settings = Settings.from_environment()

    assert settings.langfuse_host == "https://project.example"


def test_production_without_api_auth_fails_closed():
    with pytest.raises(RuntimeError, match="生产环境必须配置"):
        Settings(env="production").validate_runtime()


def test_production_accepts_single_api_key():
    Settings(env="production", api_key="single-secret").validate_runtime()


def test_production_accepts_non_empty_scoped_api_keys():
    settings = Settings(
        env="production",
        api_keys_json=json.dumps({"analyst-key": "restricted_analyst"}),
    )

    settings.validate_runtime()


def test_production_rejects_empty_scoped_api_key_map():
    with pytest.raises(RuntimeError, match="生产环境必须配置"):
        Settings(env="production", api_keys_json="{}").validate_runtime()


def test_scoped_api_key_map_rejects_empty_key_or_scope():
    for payload in ({"": "default"}, {"key": ""}):
        with pytest.raises(ValueError, match="不能为空"):
            Settings(api_keys_json=json.dumps(payload)).validate_runtime()


def test_development_without_api_auth_remains_available():
    Settings(env="development").validate_runtime()


def test_from_environment_enforces_production_auth(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TEXT2SQL_ENV", "production")
    monkeypatch.delenv("TEXT2SQL_API_KEY", raising=False)
    monkeypatch.delenv("TEXT2SQL_API_KEYS_JSON", raising=False)

    with pytest.raises(RuntimeError, match="生产环境必须配置"):
        Settings.from_environment()


def test_compose_forwards_scoped_api_keys():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert "TEXT2SQL_API_KEYS_JSON: ${TEXT2SQL_API_KEYS_JSON:-}" in compose


def test_compose_database_credentials_and_internal_ports_fail_closed():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert "${POSTGRES_ADMIN_PASSWORD:?POSTGRES_ADMIN_PASSWORD is required}" in compose
    assert (
        "${TEXT2SQL_READONLY_PASSWORD:?TEXT2SQL_READONLY_PASSWORD is required}" in compose
    )
    assert "local_admin_change_me" not in compose
    assert "local_readonly_change_me" not in compose
    assert (
        '"${TEXT2SQL_BIND_HOST:-127.0.0.1}:${TEXT2SQL_POSTGRES_PORT:-15432}:5432"'
        in compose
    )
    assert (
        '"${TEXT2SQL_BIND_HOST:-127.0.0.1}:${TEXT2SQL_REDIS_PORT:-16379}:6379"'
        in compose
    )
    assert (
        '"${TEXT2SQL_BIND_HOST:-127.0.0.1}:${TEXT2SQL_API_PORT:-18000}:8000"'
        in compose
    )
