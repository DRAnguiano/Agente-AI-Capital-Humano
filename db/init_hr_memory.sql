CREATE TABLE IF NOT EXISTS rh_conversations (
    id BIGSERIAL PRIMARY KEY,
    channel TEXT NOT NULL,
    channel_user_id TEXT NOT NULL,
    conversation_key TEXT UNIQUE NOT NULL,
    candidate_name TEXT,
    current_stage TEXT DEFAULT 'START',
    status TEXT DEFAULT 'OPEN',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rh_messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_key TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rh_candidate_profile (
    id BIGSERIAL PRIMARY KEY,
    conversation_key TEXT UNIQUE NOT NULL,
    nombre_completo TEXT,
    edad INT,
    ciudad TEXT,
    telefono TEXT,
    experiencia_quinta_rueda TEXT,
    licencia_federal TEXT,
    tipo_licencia TEXT,
    apto_medico TEXT,
    disponibilidad_viajar TEXT,
    ultimo_empleo TEXT,
    motivo_salida TEXT,
    documentos TEXT,
    perfil_status TEXT DEFAULT 'EN_PROCESO',
    score INT DEFAULT 0,
    observaciones TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rh_conversations_key
ON rh_conversations (conversation_key);

CREATE INDEX IF NOT EXISTS idx_rh_messages_conversation_time
ON rh_messages (conversation_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rh_candidate_profile_key
ON rh_candidate_profile (conversation_key);
