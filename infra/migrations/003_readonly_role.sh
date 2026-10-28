#!/bin/sh
set -eu

psql --set ON_ERROR_STOP=1 --set readonly_password="$TEXT2SQL_READONLY_PASSWORD" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'text2sql_readonly') THEN
    CREATE ROLE text2sql_readonly LOGIN;
  END IF;
END
\$\$;
ALTER ROLE text2sql_readonly PASSWORD :'readonly_password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO text2sql_readonly;
GRANT USAGE ON SCHEMA public TO text2sql_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO text2sql_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO text2sql_readonly;
ALTER ROLE text2sql_readonly SET default_transaction_read_only = on;
ALTER ROLE text2sql_readonly SET statement_timeout = '5s';
ALTER ROLE text2sql_readonly SET lock_timeout = '1s';
EOSQL

