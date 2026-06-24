-- =========================================================
-- 003_lead_memory_v2.sql
-- Memoria operativa limpia para leads RH.
--
-- Principio de diseño:
-- - PostgreSQL recuerda hechos, estado y eventos del lead.
-- - PostgreSQL NO gobierna rígidamente la conversación.
-- - Neo4j enruta intención/conocimiento.
-- - El LLM conversa con memoria como contexto, no como jaula.
--
-- Seguro para correr varias veces: usa CREATE IF NOT EXISTS,
-- ALTER IF NOT EXISTS y ON CONFLICT en catálogos.
-- =========================================================

BEGIN;

-- ---------------------------------------------------------
-- 1) Lead canónico
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS rh_leads_v2 (
    id BIGSERIAL PRIMARY KEY,
    lead_key TEXT UNIQUE NOT NULL,

    display_name TEXT,
    phone TEXT,
    source_channel TEXT,

    -- Resumen operativo para RH / dashboard.
    lead_status TEXT NOT NULL DEFAULT 'open',
    funnel_stage TEXT NOT NULL DEFAULT 'new',
    next_best_action TEXT,

    -- Resumen flexible. No debe usarse como regla dura de conversación.
    memory_summary TEXT,
    facts_summary JSONB NOT NULL DEFAULT '{}'::jsonb,

    risk_level TEXT NOT NULL DEFAULT 'low',
    requires_human BOOLEAN NOT NULL DEFAULT false,

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT rh_leads_v2_status_check
        CHECK (lead_status IN ('open', 'followup_pending', 'human_review', 'closed', 'lost')),
    CONSTRAINT rh_leads_v2_risk_check
        CHECK (risk_level IN ('low', 'medium', 'high'))
);

CREATE INDEX IF NOT EXISTS idx_rh_leads_v2_status_stage
ON rh_leads_v2 (lead_status, funnel_stage);

CREATE INDEX IF NOT EXISTS idx_rh_leads_v2_updated_at
ON rh_leads_v2 (updated_at DESC);

-- ---------------------------------------------------------
-- 2) Conversaciones / canales conectados al mismo lead
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS rh_lead_conversations_v2 (
    id BIGSERIAL PRIMARY KEY,
    lead_key TEXT NOT NULL REFERENCES rh_leads_v2(lead_key) ON DELETE CASCADE,

    conversation_key TEXT UNIQUE NOT NULL,
    channel TEXT NOT NULL,
    channel_user_id TEXT,

    chatwoot_account_id TEXT,
    chatwoot_inbox_id TEXT,
    chatwoot_conversation_id TEXT,
    chatwoot_contact_id TEXT,

    is_primary BOOLEAN NOT NULL DEFAULT true,
    external_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rh_lead_conversations_v2_lead
ON rh_lead_conversations_v2 (lead_key);

CREATE INDEX IF NOT EXISTS idx_rh_lead_conversations_v2_chatwoot
ON rh_lead_conversations_v2 (chatwoot_conversation_id);

-- ---------------------------------------------------------
-- 3) Mensajes crudos
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS rh_lead_messages_v2 (
    id BIGSERIAL PRIMARY KEY,
    lead_key TEXT NOT NULL REFERENCES rh_leads_v2(lead_key) ON DELETE CASCADE,
    conversation_key TEXT NOT NULL,

    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'internal')),
    message TEXT NOT NULL,

    source_message_id TEXT,
    external_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rh_lead_messages_v2_lead_time
ON rh_lead_messages_v2 (lead_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rh_lead_messages_v2_conv_time
ON rh_lead_messages_v2 (conversation_key, created_at DESC);

-- ---------------------------------------------------------
-- 4) Hechos flexibles del lead
-- Ejemplos:
-- role_fit/operator_type = operador_5ta_rueda
-- document/apto_status = expires_in_2_months
-- documents/general_status = pending
-- interest/payment = asked
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS rh_lead_facts_v2 (
    id BIGSERIAL PRIMARY KEY,
    lead_key TEXT NOT NULL REFERENCES rh_leads_v2(lead_key) ON DELETE CASCADE,

    fact_group TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    fact_value_json JSONB,

    confidence NUMERIC(4,3) NOT NULL DEFAULT 0.700,
    source TEXT NOT NULL DEFAULT 'conversation',
    source_message_id BIGINT,
    source_text TEXT,

    is_active BOOLEAN NOT NULL DEFAULT true,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT rh_lead_facts_v2_unique_active
        UNIQUE (lead_key, fact_group, fact_key, is_active)
);

CREATE INDEX IF NOT EXISTS idx_rh_lead_facts_v2_lookup
ON rh_lead_facts_v2 (lead_key, fact_group, fact_key)
WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_rh_lead_facts_v2_group_value
ON rh_lead_facts_v2 (fact_group, fact_key, fact_value)
WHERE is_active = true;

-- ---------------------------------------------------------
-- 5) Eventos para analítica / embudo
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS rh_lead_events_v2 (
    id BIGSERIAL PRIMARY KEY,
    lead_key TEXT NOT NULL REFERENCES rh_leads_v2(lead_key) ON DELETE CASCADE,
    conversation_key TEXT,

    event_type TEXT NOT NULL,
    intent TEXT,
    route TEXT,

    stage_from TEXT,
    stage_to TEXT,
    risk_level TEXT NOT NULL DEFAULT 'low',
    requires_human BOOLEAN NOT NULL DEFAULT false,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT rh_lead_events_v2_risk_check
        CHECK (risk_level IN ('low', 'medium', 'high'))
);

CREATE INDEX IF NOT EXISTS idx_rh_lead_events_v2_lead_time
ON rh_lead_events_v2 (lead_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rh_lead_events_v2_event_type
ON rh_lead_events_v2 (event_type);

CREATE INDEX IF NOT EXISTS idx_rh_lead_events_v2_stage
ON rh_lead_events_v2 (stage_to);

-- ---------------------------------------------------------
-- 6) Catálogo de etapas del embudo
-- No es gobernador conversacional: es taxonomía para RH/Power BI.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS rh_funnel_stage_catalog_v2 (
    stage_key TEXT PRIMARY KEY,
    stage_label TEXT NOT NULL,
    stage_order INT NOT NULL,
    description TEXT,
    is_terminal BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO rh_funnel_stage_catalog_v2 (stage_key, stage_label, stage_order, description, is_terminal)
VALUES
    ('new', 'Nuevo lead', 10, 'Lead recién creado o primera interacción.', false),
    ('interested', 'Interesado', 20, 'Mostró interés inicial por la vacante.', false),
    ('vacancy_info_shared', 'Información de vacante compartida', 30, 'Se compartieron detalles como pago, ruta, requisitos o condiciones.', false),
    ('profile_hint_collected', 'Perfil preliminar detectado', 40, 'El candidato mencionó datos útiles como operador de quinta rueda, ciudad o experiencia.', false),
    ('documents_pending', 'Documentos pendientes', 50, 'Se solicitaron o quedaron pendientes documentos.', false),
    ('documents_received', 'Documentos recibidos / por validar', 60, 'El candidato indica que ya envió documentos.', false),
    ('apto_pending_update', 'Apto médico por actualizar', 70, 'El candidato menciona apto vencido o próximo a vencer.', false),
    ('safety_review', 'Revisión de seguridad', 80, 'Se detectó tema de pruebas, cero tolerancia o validación sensible.', false),
    ('followup_pending', 'Seguimiento pendiente', 90, 'El candidato se despide, pide retomar después o queda pendiente seguimiento.', false),
    ('human_review', 'Revisión humana', 95, 'Capital Humano debe revisar antes de continuar.', false),
    ('lost', 'Perdido / abandonó', 100, 'Lead abandonó o eligió otra opción.', true),
    ('closed', 'Cerrado', 110, 'Proceso cerrado de forma explícita.', true)
ON CONFLICT (stage_key) DO UPDATE SET
    stage_label = EXCLUDED.stage_label,
    stage_order = EXCLUDED.stage_order,
    description = EXCLUDED.description,
    is_terminal = EXCLUDED.is_terminal;

-- ---------------------------------------------------------
-- 7) Vista para Chatwoot / Power BI / notas internas
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW v_rh_lead_memory_v2 AS
SELECT
    l.lead_key,
    l.display_name,
    l.phone,
    l.source_channel,
    l.lead_status,
    l.funnel_stage,
    c.stage_label AS funnel_stage_label,
    c.stage_order AS funnel_stage_order,
    l.next_best_action,
    l.memory_summary,
    l.facts_summary,
    l.risk_level,
    l.requires_human,
    l.first_seen_at,
    l.last_seen_at,
    l.updated_at,
    (
        SELECT jsonb_object_agg(f.fact_group || '.' || f.fact_key, f.fact_value)
        FROM rh_lead_facts_v2 f
        WHERE f.lead_key = l.lead_key
          AND f.is_active = true
    ) AS active_facts,
    (
        SELECT jsonb_agg(
            jsonb_build_object(
                'event_type', e.event_type,
                'intent', e.intent,
                'route', e.route,
                'stage_to', e.stage_to,
                'created_at', e.created_at
            ) ORDER BY e.created_at DESC
        )
        FROM (
            SELECT *
            FROM rh_lead_events_v2 e
            WHERE e.lead_key = l.lead_key
            ORDER BY e.created_at DESC
            LIMIT 10
        ) e
    ) AS recent_events
FROM rh_leads_v2 l
LEFT JOIN rh_funnel_stage_catalog_v2 c
    ON c.stage_key = l.funnel_stage;

COMMIT;
