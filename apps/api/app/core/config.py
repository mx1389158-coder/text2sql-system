from __future__ import annotations

import os
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Settings(BaseModel):
    model_config = {"extra": "ignore"}

    env: str = "development"
    api_key: str = ""
    api_keys_json: str = ""
    database_url: str = "sqlite:///./data/snapshots/demo.db"
    database_schema: str = "main"
    catalog_path: Path = Path("data/processed/catalog_v1.json")
    semantic_catalog_path: Path = Path("data/processed/semantic_catalog_v1.json")
    llm_provider: Literal["demo", "openai-compatible"] = "demo"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5-coder:3b"
    model_timeout_seconds: float = 60
    model_max_tokens: int = Field(default=256, ge=64, le=4096)
    statement_timeout_ms: int = 5000
    lock_timeout_ms: int = 1000
    max_rows: int = Field(default=200, ge=1, le=1000)
    schema_top_k: int = Field(default=6, ge=1, le=20)
    schema_max_top_k: int = Field(default=12, ge=1, le=23)
    schema_dense_weight: float = Field(default=0.35, ge=0, le=1)
    schema_token_budget: int = Field(default=3000, ge=500, le=16000)
    max_repair_rounds: int = Field(default=2, ge=0, le=2)
    candidate_count: int = Field(default=3, ge=1, le=3)
    candidate_semantic_threshold: float = Field(default=0.65, ge=0, le=1)
    cache_ttl_seconds: int = Field(default=300, ge=0, le=86400)
    schema_cache_ttl_seconds: int = Field(default=3600, ge=0, le=86400)
    few_shot_path: Path = Path("training/datasets/raw/train.jsonl")
    # Two diverse examples were more reliable than three on multi-hop joins:
    # the third example tended to introduce unrelated filters into the SQL.
    few_shot_count: int = Field(default=2, ge=0, le=8)
    enable_few_shots: bool = True
    enable_fk_completion: bool = True
    enable_adaptive_schema: bool = True
    state_database_path: Path = Path("data/state/text2sql-state.db")
    access_policy_path: Path = Path("data/security/access_policy.json")
    rate_limit_requests: int = Field(default=60, ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    max_concurrent_requests: int = Field(default=8, ge=1, le=256)
    evaluation_concurrency: int = Field(default=1, ge=1, le=8)
    evaluation_allowed_root: Path = Path("data")
    model_parse_retries: int = Field(default=1, ge=0, le=3)
    langfuse_host: Optional[str] = None
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None

    @classmethod
    def from_environment(cls) -> "Settings":
        values = {}
        langfuse_aliases = {
            "LANGFUSE_BASE_URL": "langfuse_host",
            "LANGFUSE_PUBLIC_KEY": "langfuse_public_key",
            "LANGFUSE_SECRET_KEY": "langfuse_secret_key",
        }
        env_file = Path(".env")
        if env_file.exists():
            file_values = {}
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                file_values[key] = value
                if key.startswith("TEXT2SQL_"):
                    values[key[len("TEXT2SQL_") :].lower()] = value
            for key, field_name in langfuse_aliases.items():
                if field_name not in values and file_values.get(key):
                    values[field_name] = file_values[key]
        for field_name in cls.model_fields:
            key = f"TEXT2SQL_{field_name.upper()}"
            if os.environ.get(key):
                values[field_name] = os.environ[key]
        for key, field_name in langfuse_aliases.items():
            project_key = f"TEXT2SQL_{field_name.upper()}"
            if not os.environ.get(project_key) and os.environ.get(key):
                values[field_name] = os.environ[key]
        settings = cls(**values)
        settings.validate_runtime()
        return settings

    def validate_runtime(self) -> None:
        single_key_configured = bool(self.api_key.strip())
        scoped_keys = self.api_key_scopes() if self.api_keys_json.strip() else {}
        if self.env.strip().lower() == "production" and not (
            single_key_configured or scoped_keys
        ):
            raise RuntimeError(
                "生产环境必须配置 TEXT2SQL_API_KEY 或 TEXT2SQL_API_KEYS_JSON"
            )

    def api_key_scopes(self) -> dict[str, str]:
        if not self.api_keys_json:
            return {}
        value = json.loads(self.api_keys_json)
        if not isinstance(value, dict):
            raise ValueError("TEXT2SQL_API_KEYS_JSON 必须是 API Key 到 scope 的 JSON object")
        result = {
            str(key).strip(): str(scope).strip() for key, scope in value.items()
        }
        if any(not key or not scope for key, scope in result.items()):
            raise ValueError("TEXT2SQL_API_KEYS_JSON 的 API Key 和 scope 不能为空")
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings.from_environment()

