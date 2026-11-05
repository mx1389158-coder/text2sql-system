# Scope and cache hardening report (v1.1.1)

Verified on 2026-11-05 (Asia/Shanghai).

## Authorization changes

| Control | Result |
| --- | --- |
| `QueryRecord.scope` persisted in an indexed SQLite column | Pass |
| `GET /query/{id}` requires the current scope | Pass; mismatch returns 404 |
| `GET /queries` executes a scope-filtered repository query | Pass |
| Clarification and feedback cannot reference a foreign-scope query | Pass; mismatch returns 404 |
| Feedback history is filtered by scope | Pass |
| Schema endpoint filters tables, columns, FK edges and sample values | Pass |
| Existing query ID cannot be reassigned to another scope | Pass |
| Legacy records without ownership are inaccessible to normal scopes | Pass |
| Missing policy file and unknown scope deny all Schema access | Pass |

The repository applies ownership checks in addition to router checks. This prevents another caller
from bypassing HTTP authorization by reusing the service or persistence layer directly.

## Cache isolation changes

The result-cache key now includes:

- normalized question and clarification;
- scope and access-policy content version;
- strategy and generation-runtime version;
- model ID and Prompt version;
- Schema, semantic-catalog and Few-shot data versions.

Schema-evidence and Few-shot caches also include scope, policy version and their relevant strategy
configuration. A result-cache value contains only reusable Schema evidence, SQL, rows, explanation
and assumptions. Query ID, trace ID, session, timestamps, trace events, execution latency, model
calls, token usage and repair counters are generated or reset for the current request.

## Regression evidence

- `tests/security/test_scope_isolation.py`: attacker/analyst/admin detail, list, clarification,
  feedback and Schema-catalog isolation.
- `tests/unit/test_persistence.py`: indexed scope round-trip, legacy migration and immutable owner.
- `tests/unit/test_access_policy.py`: missing configuration and unknown scope fail-closed behavior.
- `tests/unit/test_retrieval_and_cache.py`: independent cache keys for all governed dimensions and
  request-metadata stripping.
- `tests/integration/test_orchestrator.py`: real cache hit metadata and baseline/optimized isolation.

Metric wording in README, project status and the v5 model card explicitly describes E21 as
execution accuracy on the fixed 300-example holdout under the governed Schema. It is not presented
as unrestricted Text2SQL accuracy.
