# SQL execution threat model

The attacker can control the natural-language question and may influence model output. The model is
therefore untrusted. Four controls are independent:

1. API input length, optional API key and rate-limit integration point.
2. SQLGlot parsing, one-statement SELECT/WITH policy, table scope, function controls and enforced
   outer LIMIT.
3. A dedicated PostgreSQL login with SELECT-only grants and default read-only transactions.
4. Per-transaction statement/lock timeouts and a hard row cap.

Scope policies may restrict schemas, tables and columns independently. M-Schema sample values are
only emitted for explicitly permitted table/column pairs. A column-restricted scope rejects
`SELECT *`, preventing execution from bypassing prompt-time field filtering.

Query history is also an authorization boundary. Every `QueryRecord` persists its API-key scope in
an indexed database column. Detail, clarification, feedback and list operations require the current
scope; a scope mismatch is returned as 404 so query-ID existence is not disclosed. Records created
before this field existed are marked `__legacy_unscoped__` and are not assigned to a user scope.
Changing the owner scope of an existing query ID is rejected by the repository.
The `/schema` response uses the same policy and removes unauthorized tables, columns, foreign-key
edges and sample values, so the visualization endpoint cannot bypass Schema Linking permissions.

Access-policy loading is fail-closed. A missing file or an unknown scope resolves to no schemas and
no tables. The explicit `AccessPolicy.allow_all()` constructor is reserved for isolated tests and
local smoke demos; production dependencies always load the versioned policy file.

Result-cache keys include the normalized question and clarification plus scope, policy content
version, strategy, model ID, Prompt version, Schema version, semantic-catalog version, Few-shot data
version and generation runtime version. Cached values contain only reusable inference output. A cache
hit receives a new query ID, trace ID, session, timestamps and trace, with zero model calls and token
usage for that request. Schema and Few-shot caches use the same scope/policy isolation principle.

Prompt instructions are not a security boundary. Safety rejection is deterministic and is not fed
back to the model for a bypass attempt. Production should add network isolation, secret rotation,
request rate limiting and database audit logs.

