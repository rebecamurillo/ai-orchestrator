#!/bin/bash
# One postgres server, two databases: Langfuse's and LiteLLM's.
#
# `POSTGRES_DB=langfuse` creates the first; LiteLLM's virtual keys and spend logs need their
# own, and its Prisma migration will not create the database itself. This runs once, on an
# empty data directory, which is why `make platform-down` keeps the volume and only
# `docker compose -f deploy/llm-platform/docker-compose.yml down -v` re-triggers it.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE DATABASE litellm;
	GRANT ALL PRIVILEGES ON DATABASE litellm TO "$POSTGRES_USER";
EOSQL

echo "llm-platform stack: created database 'litellm' beside '$POSTGRES_DB'"
