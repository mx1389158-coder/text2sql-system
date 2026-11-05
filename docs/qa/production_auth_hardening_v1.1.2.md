# Production authentication hardening (v1.1.2)

Verified on 2026-11-05 (Asia/Shanghai).

## Startup invariant

`Settings.from_environment()` invokes `validate_runtime()` before the application is constructed.

| Runtime | Authentication configuration | Result |
| --- | --- | --- |
| development | neither key mode configured | Allowed for local demo |
| production | `TEXT2SQL_API_KEY` non-empty | Allowed |
| production | non-empty valid `TEXT2SQL_API_KEYS_JSON` | Allowed |
| production | neither configured | Startup raises `RuntimeError` |
| production | empty JSON object | Startup raises `RuntimeError` |
| any mode | multi-key entry has an empty key or scope | Configuration error |

This prevents an omitted production secret from falling back to the full-access `default` scope.

## Deployment path

- `docker-compose.yml` forwards both `TEXT2SQL_API_KEY` and `TEXT2SQL_API_KEYS_JSON`.
- `.env.example` documents the production requirement.
- `scripts/generate_deployment_secrets.py` creates a non-empty single API key for new deployments.
- `scripts/ensure_api_auth.py` safely adds a key to an existing ignored `.env` only when both auth
  modes are empty. It never prints the generated value and preserves all existing settings.
- `scripts/deploy_virtualbox.py --env-file .env` uploads that ignored file atomically with mode 0600;
  deployment evidence records only a boolean and never stores secret values.
- The Web client accepts an API key, keeps it in `sessionStorage`, and sends it as `X-API-Key`.
  The key is not embedded in the JavaScript bundle or persisted in project files.

## Tests

- `tests/unit/test_config.py`: development/production matrix, empty maps, malformed entries and
  Compose forwarding.
- `tests/unit/test_ensure_api_auth.py`: non-overwrite and multi-key preservation.
- `tests/e2e/test_api.py`: authenticated query, clarification and SSE pipeline.
- Vue typecheck and production build cover the browser authentication control.
