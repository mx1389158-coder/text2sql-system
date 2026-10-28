# SQL execution threat model

The attacker can control the natural-language question and may influence model output. The model is
therefore untrusted. Four controls are independent:

1. API input length, optional API key and rate-limit integration point.
2. SQLGlot parsing, one-statement SELECT/WITH policy, table scope, function controls and enforced
   outer LIMIT.
3. A dedicated PostgreSQL login with SELECT-only grants and default read-only transactions.
4. Per-transaction statement/lock timeouts and a hard row cap.

Prompt instructions are not a security boundary. Safety rejection is deterministic and is not fed
back to the model for a bypass attempt. Production should add network isolation, secret rotation,
request rate limiting and database audit logs.

