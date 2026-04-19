-- Migration 001: core tables
-- Apply with: psql $DATABASE_URL -f backend/db/migrations/001_init.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── users ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    is_active     BOOLEAN     NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ── sessions ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal              TEXT        NOT NULL,
    status            TEXT        NOT NULL CHECK (status IN ('pending','running','completed','failed','aborted')),
    final_output      JSONB,
    final_quality     REAL,
    iteration_count   INTEGER     NOT NULL DEFAULT 0,
    total_tokens_in   INTEGER     NOT NULL DEFAULT 0,
    total_tokens_out  INTEGER     NOT NULL DEFAULT 0,
    total_cost_usd    NUMERIC(10,4) NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_created ON sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_status       ON sessions(status) WHERE status = 'running';

-- ── audit_log ─────────────────────────────────────────────────────────────────
-- BIGSERIAL PK for insert throughput (per spec: UUIDs everywhere except audit_log)
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    agent_name  TEXT        NOT NULL, -- planner | researcher | executor | verifier | reflector
    iteration   INTEGER     NOT NULL,
    model_used  TEXT        NOT NULL,
    tokens_in   INTEGER     NOT NULL,
    tokens_out  INTEGER     NOT NULL,
    latency_ms  INTEGER     NOT NULL,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id, created_at);

-- ── quality_metrics ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quality_metrics (
    id            BIGSERIAL   PRIMARY KEY,
    session_id    UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    iteration     INTEGER     NOT NULL,
    overall_score REAL        NOT NULL,
    completeness  REAL        NOT NULL,
    accuracy      REAL        NOT NULL,
    quality       REAL        NOT NULL,
    efficiency    REAL        NOT NULL,
    format_score  REAL        NOT NULL,
    directives    JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
