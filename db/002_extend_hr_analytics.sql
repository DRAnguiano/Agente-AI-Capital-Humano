-- =========================================================
-- 002_extend_hr_analytics.sql
-- Extiende la memoria RH para analítica, handoff humano,
-- Chatwoot/WhatsApp y auditoría RAG.
-- No rompe tablas existentes.
-- =========================================================

BEGIN;

-- 1) Eventos analíticos del candidato
CREATE TABLE IF NOT EXISTS rh_candidate_events (
    id BIGSERIAL PRIMARY KEY,
    conversation_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    stage_from TEXT,
    stage_to TEXT,
    intent TEXT,
    risk_level TEXT DEFAULT 'low',
    requires_human BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rh_candidate_events_key_time
ON rh_candidate_events (conversation_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rh_candidate_events_type
ON rh_candidate_events (event_type);

CREATE INDEX IF NOT EXISTS idx_rh_candidate_events_risk
ON rh_candidate_events (risk_level);


-- 2) Fallback / handoff humano
CREATE TABLE IF NOT EXISTS rh_human_handoffs (
    id BIGSERIAL PRIMARY KEY,
    conversation_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    risk_level TEXT DEFAULT 'high',
    assigned_to TEXT,
    status TEXT DEFAULT 'OPEN',
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    CONSTRAINT rh_human_handoffs_status_check
        CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CANCELLED'))
);

CREATE INDEX IF NOT EXISTS idx_rh_handoffs_key_time
ON rh_human_handoffs (conversation_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rh_handoffs_status
ON rh_human_handoffs (status);


-- 3) Identidades externas por canal
-- Sirve para mapear Telegram, WhatsApp, Chatwoot, Webchat, etc.
CREATE TABLE IF NOT EXISTS rh_channel_identities (
    id BIGSERIAL PRIMARY KEY,
    conversation_key TEXT NOT NULL,
    channel TEXT NOT NULL,
    channel_user_id TEXT,
    phone TEXT,
    username TEXT,
    chatwoot_contact_id TEXT,
    chatwoot_conversation_id TEXT,
    external_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT rh_channel_identity_unique
        UNIQUE (channel, channel_user_id)
);

CREATE INDEX IF NOT EXISTS idx_rh_channel_identities_key
ON rh_channel_identities (conversation_key);

CREATE INDEX IF NOT EXISTS idx_rh_channel_identities_phone
ON rh_channel_identities (phone);


-- 4) Auditoría RAG
-- Guarda qué fuentes se usaron para responder.
CREATE TABLE IF NOT EXISTS rh_rag_audit (
    id BIGSERIAL PRIMARY KEY,
    conversation_key TEXT NOT NULL,
    user_message TEXT NOT NULL,
    answer TEXT,
    sources JSONB DEFAULT '[]'::jsonb,
    top_k INT,
    min_score NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rh_rag_audit_key_time
ON rh_rag_audit (conversation_key, created_at DESC);


-- 5) Columnas adicionales útiles en rh_conversations
ALTER TABLE rh_conversations
ADD COLUMN IF NOT EXISTS last_intent TEXT;

ALTER TABLE rh_conversations
ADD COLUMN IF NOT EXISTS risk_level TEXT DEFAULT 'low';

ALTER TABLE rh_conversations
ADD COLUMN IF NOT EXISTS requires_human BOOLEAN DEFAULT false;

ALTER TABLE rh_conversations
ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMPTZ;

ALTER TABLE rh_conversations
ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;


-- 6) Columnas adicionales útiles en rh_candidate_profile
ALTER TABLE rh_candidate_profile
ADD COLUMN IF NOT EXISTS source TEXT;

ALTER TABLE rh_candidate_profile
ADD COLUMN IF NOT EXISTS vacancy TEXT;

ALTER TABLE rh_candidate_profile
ADD COLUMN IF NOT EXISTS last_detected_intent TEXT;

ALTER TABLE rh_candidate_profile
ADD COLUMN IF NOT EXISTS risk_level TEXT DEFAULT 'low';

ALTER TABLE rh_candidate_profile
ADD COLUMN IF NOT EXISTS requires_human BOOLEAN DEFAULT false;

ALTER TABLE rh_candidate_profile
ADD COLUMN IF NOT EXISTS profile_completed_at TIMESTAMPTZ;

COMMIT;

