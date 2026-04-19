-- Runs once on first container boot via docker-entrypoint-initdb.d
-- The database and user are already created by POSTGRES_USER/DB env vars;
-- this file handles any additional bootstrap needed.

-- Ensure pgcrypto is available for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Ensure the nexus user has full rights on the nexus database
-- (already the owner when POSTGRES_USER=nexus, but guard for overrides)
GRANT ALL PRIVILEGES ON DATABASE nexus TO nexus;
