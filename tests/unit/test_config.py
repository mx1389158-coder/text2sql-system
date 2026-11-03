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
