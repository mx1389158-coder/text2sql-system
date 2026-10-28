# Infrastructure

The root `docker-compose.yml` starts PostgreSQL, the API and the Vue development server.
Redis is optional and starts with `docker compose --profile cache up`. Langfuse should be run
from its upstream pinned compose release rather than copied into this repository.

The database init order is deliberate: schema, deterministic seed, then the read-only role.
Changing the schema requires rebuilding the development volume or applying a numbered migration.

