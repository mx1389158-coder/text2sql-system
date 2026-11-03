# Infrastructure

The root `docker-compose.yml` starts PostgreSQL, the API and the Vue development server.
Redis is optional and starts with `docker compose --profile cache up`. The release uses Langfuse
Cloud through credentials stored in the ignored `.env`. If self-hosting is required later, run an
upstream pinned Langfuse compose release rather than copying its stack into this repository.

The database init order is deliberate: schema, deterministic seed, then the read-only role.
Changing the schema requires rebuilding the development volume or applying a numbered migration.

