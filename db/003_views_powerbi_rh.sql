-- =========================================================
-- 003_views_powerbi_rh.sql
-- Vistas analíticas para Power BI / Capital Humano
-- Proyecto: Agente RH Operadores Quinta Rueda
-- =========================================================

BEGIN;

-- =========================================================
-- 1) Vista principal del pipeline de candidatos
-- =========================================================
CREATE OR REPLACE VIEW v_rh_candidate_pipeline AS
SELECT
    c.conversation_key,
    c.channel,
    c.channel_user_id,
    c.candidate_name,
    c.current_stage,
    c.status,
    c.last_intent,
    c.risk_level,
    c.requires_human,
    c.created_at AS conversation_created_at,
    c.updated_at AS conversation_updated_at,
    c.last_message_at,
    c.closed_at,

    p.nombre_completo,
    p.edad,
    p.ciudad,
    p.telefono,
    p.experiencia_quinta_rueda,
    p.licencia_federal,
    p.tipo_licencia,
    p.apto_medico,
    p.disponibilidad_viajar,
    p.ultimo_empleo,
    p.motivo_salida,
    p.documentos,
    p.perfil_status,
    p.score,
    p.observaciones,
    p.source,
    p.vacancy,
    p.last_detected_intent,
    p.profile_completed_at,

    CASE
        WHEN c.current_stage = 'START' THEN 'Inicio'
        WHEN c.current_stage = 'ASK_CITY' THEN 'Ciudad pendiente'
        WHEN c.current_stage = 'ASK_LICENSE' THEN 'Licencia pendiente'
        WHEN c.current_stage = 'ASK_EXPERIENCE' THEN 'Experiencia pendiente'
        WHEN c.current_stage = 'ASK_APTO' THEN 'Apto médico pendiente'
        WHEN c.current_stage = 'ASK_AVAILABILITY' THEN 'Disponibilidad pendiente'
        WHEN c.current_stage = 'PROFILE_READY' THEN 'Perfil listo'
        WHEN c.current_stage = 'CLARIFY_AMBIGUOUS_SLANG' THEN 'Aclaración pendiente'
        WHEN c.current_stage = 'HUMAN_REVIEW_REQUIRED' THEN 'Revisión humana requerida'
        ELSE c.current_stage
    END AS stage_label,

    CASE
        WHEN c.current_stage = 'PROFILE_READY' THEN true
        ELSE false
    END AS is_profile_ready,

    CASE
        WHEN c.requires_human = true OR c.current_stage = 'HUMAN_REVIEW_REQUIRED' THEN true
        ELSE false
    END AS needs_human_review,

    CASE
        WHEN p.ciudad IS NOT NULL
         AND p.licencia_federal IS NOT NULL
         AND p.experiencia_quinta_rueda IS NOT NULL
         AND p.apto_medico IS NOT NULL
         AND p.disponibilidad_viajar IS NOT NULL
        THEN true
        ELSE false
    END AS has_basic_profile_complete,

    now() - c.updated_at AS time_since_last_update

FROM rh_conversations c
LEFT JOIN rh_candidate_profile p
    ON p.conversation_key = c.conversation_key;


-- =========================================================
-- 2) Vista de mensajes con datos de conversación
-- =========================================================
CREATE OR REPLACE VIEW v_rh_messages AS
SELECT
    m.id AS message_id,
    m.conversation_key,
    c.channel,
    c.channel_user_id,
    c.current_stage,
    c.risk_level,
    c.requires_human,
    m.role,
    m.message,
    m.created_at,

    DATE(m.created_at) AS message_date,
    EXTRACT(HOUR FROM m.created_at) AS message_hour,

    CASE
        WHEN m.role IN ('user', 'candidate') THEN 'Candidato'
        WHEN m.role IN ('assistant', 'bot') THEN 'Bot'
        WHEN m.role IN ('human', 'agent') THEN 'Humano'
        ELSE m.role
    END AS sender_label,

    LENGTH(m.message) AS message_length

FROM rh_messages m
LEFT JOIN rh_conversations c
    ON c.conversation_key = m.conversation_key;


-- =========================================================
-- 3) Vista diaria de volumen de mensajes
-- =========================================================
CREATE OR REPLACE VIEW v_rh_messages_daily AS
SELECT
    DATE(created_at) AS message_date,
    conversation_key,

    COUNT(*) AS total_messages,

    COUNT(*) FILTER (
        WHERE role IN ('user', 'candidate')
    ) AS candidate_messages,

    COUNT(*) FILTER (
        WHERE role IN ('assistant', 'bot')
    ) AS bot_messages,

    COUNT(*) FILTER (
        WHERE role IN ('human', 'agent')
    ) AS human_messages,

    MIN(created_at) AS first_message_at,
    MAX(created_at) AS last_message_at

FROM rh_messages
GROUP BY
    DATE(created_at),
    conversation_key;


-- =========================================================
-- 4) Vista de eventos del proceso
-- =========================================================
CREATE OR REPLACE VIEW v_rh_candidate_events AS
SELECT
    e.id AS event_id,
    e.conversation_key,
    c.channel,
    c.channel_user_id,
    e.event_type,
    e.stage_from,
    e.stage_to,
    e.intent,
    e.risk_level,
    e.requires_human,
    e.metadata,
    e.created_at,

    DATE(e.created_at) AS event_date,
    EXTRACT(HOUR FROM e.created_at) AS event_hour,

    CASE
        WHEN e.event_type = 'message_received' THEN 'Mensaje recibido'
        WHEN e.event_type = 'stage_changed' THEN 'Cambio de etapa'
        WHEN e.event_type = 'rag_answered' THEN 'Respuesta RAG'
        WHEN e.event_type = 'human_handoff_created' THEN 'Handoff humano'
        WHEN e.event_type = 'clarification_requested' THEN 'Aclaración solicitada'
        WHEN e.event_type = 'followup_time_answered' THEN 'Seguimiento respondido'
        WHEN e.event_type = 'documents_complete_answered' THEN 'Documentación respondida'
        WHEN e.event_type = 'foraneo_travel_answered' THEN 'Foráneo / traslado respondido'
        ELSE e.event_type
    END AS event_label

FROM rh_candidate_events e
LEFT JOIN rh_conversations c
    ON c.conversation_key = e.conversation_key;


-- =========================================================
-- 5) Vista de handoffs humanos
-- =========================================================
CREATE OR REPLACE VIEW v_rh_handoffs AS
SELECT
    h.id AS handoff_id,
    h.conversation_key,
    c.channel,
    c.channel_user_id,
    c.current_stage,
    c.last_intent,
    h.reason,
    h.risk_level,
    h.assigned_to,
    h.status,
    h.summary,
    h.created_at,
    h.resolved_at,

    CASE
        WHEN h.resolved_at IS NOT NULL THEN h.resolved_at - h.created_at
        ELSE now() - h.created_at
    END AS handoff_age,

    CASE
        WHEN h.status = 'OPEN' THEN true
        ELSE false
    END AS is_open,

    CASE
        WHEN h.risk_level = 'high' THEN true
        ELSE false
    END AS is_high_risk

FROM rh_human_handoffs h
LEFT JOIN rh_conversations c
    ON c.conversation_key = h.conversation_key;


-- =========================================================
-- 6) Vista de uso de RAG
-- =========================================================
CREATE OR REPLACE VIEW v_rh_rag_usage AS
SELECT
    r.id AS rag_audit_id,
    r.conversation_key,
    c.channel,
    c.channel_user_id,
    r.user_message,
    r.answer,
    r.sources,
    r.top_k,
    r.min_score,
    r.created_at,

    DATE(r.created_at) AS rag_date,

    jsonb_array_length(COALESCE(r.sources, '[]'::jsonb)) AS source_count,

    CASE
        WHEN jsonb_array_length(COALESCE(r.sources, '[]'::jsonb)) > 0 THEN true
        ELSE false
    END AS has_sources

FROM rh_rag_audit r
LEFT JOIN rh_conversations c
    ON c.conversation_key = r.conversation_key;


-- =========================================================
-- 7) Vista de calidad básica del lead
-- =========================================================
CREATE OR REPLACE VIEW v_rh_lead_quality AS
SELECT
    c.conversation_key,
    c.channel,
    c.channel_user_id,
    c.current_stage,
    c.risk_level,
    c.requires_human,

    p.ciudad,
    p.licencia_federal,
    p.tipo_licencia,
    p.experiencia_quinta_rueda,
    p.apto_medico,
    p.disponibilidad_viajar,
    p.documentos,

    (
        CASE WHEN p.ciudad IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN p.licencia_federal IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN p.experiencia_quinta_rueda IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN p.apto_medico IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN p.disponibilidad_viajar IS NOT NULL THEN 1 ELSE 0 END
    ) AS completed_basic_fields,

    5 AS total_basic_fields,

    ROUND(
        (
            (
                CASE WHEN p.ciudad IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN p.licencia_federal IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN p.experiencia_quinta_rueda IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN p.apto_medico IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN p.disponibilidad_viajar IS NOT NULL THEN 1 ELSE 0 END
            )::numeric / 5::numeric
        ) * 100,
        2
    ) AS profile_completion_pct,

    CASE
        WHEN c.requires_human = true THEN 'Revisión humana'
        WHEN c.risk_level = 'high' THEN 'Alto riesgo'
        WHEN c.current_stage = 'PROFILE_READY' THEN 'Listo para RH'
        WHEN (
            CASE WHEN p.ciudad IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN p.licencia_federal IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN p.experiencia_quinta_rueda IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN p.apto_medico IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN p.disponibilidad_viajar IS NOT NULL THEN 1 ELSE 0 END
        ) >= 3 THEN 'Perfil parcial'
        ELSE 'Perfil inicial'
    END AS lead_quality_label

FROM rh_conversations c
LEFT JOIN rh_candidate_profile p
    ON p.conversation_key = c.conversation_key;


-- =========================================================
-- 8) Vista de abandono / inactividad
-- =========================================================
CREATE OR REPLACE VIEW v_rh_inactive_candidates AS
SELECT
    c.conversation_key,
    c.channel,
    c.channel_user_id,
    c.current_stage,
    c.status,
    c.last_intent,
    c.risk_level,
    c.requires_human,
    c.created_at,
    c.updated_at,
    c.last_message_at,

    p.ciudad,
    p.licencia_federal,
    p.tipo_licencia,
    p.experiencia_quinta_rueda,
    p.apto_medico,
    p.disponibilidad_viajar,

    now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) AS inactive_time,

    CASE
        WHEN now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) >= interval '48 hours'
            THEN 'Inactivo 48h+'
        WHEN now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) >= interval '24 hours'
            THEN 'Inactivo 24h+'
        WHEN now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) >= interval '4 hours'
            THEN 'Inactivo 4h+'
        ELSE 'Activo reciente'
    END AS inactivity_bucket

FROM rh_conversations c
LEFT JOIN rh_candidate_profile p
    ON p.conversation_key = c.conversation_key
WHERE c.status IS DISTINCT FROM 'CLOSED';


-- =========================================================
-- 9) Vista resumen por etapa
-- =========================================================
CREATE OR REPLACE VIEW v_rh_stage_summary AS
SELECT
    current_stage,

    CASE
        WHEN current_stage = 'START' THEN 'Inicio'
        WHEN current_stage = 'ASK_CITY' THEN 'Ciudad pendiente'
        WHEN current_stage = 'ASK_LICENSE' THEN 'Licencia pendiente'
        WHEN current_stage = 'ASK_EXPERIENCE' THEN 'Experiencia pendiente'
        WHEN current_stage = 'ASK_APTO' THEN 'Apto médico pendiente'
        WHEN current_stage = 'ASK_AVAILABILITY' THEN 'Disponibilidad pendiente'
        WHEN current_stage = 'PROFILE_READY' THEN 'Perfil listo'
        WHEN current_stage = 'CLARIFY_AMBIGUOUS_SLANG' THEN 'Aclaración pendiente'
        WHEN current_stage = 'HUMAN_REVIEW_REQUIRED' THEN 'Revisión humana requerida'
        ELSE current_stage
    END AS stage_label,

    COUNT(*) AS total_candidates,

    COUNT(*) FILTER (WHERE requires_human = true) AS candidates_requiring_human,

    COUNT(*) FILTER (WHERE risk_level = 'high') AS high_risk_candidates,

    MIN(created_at) AS first_created_at,
    MAX(updated_at) AS last_updated_at

FROM rh_conversations
GROUP BY current_stage;


-- =========================================================
-- 10) Vista resumen ejecutivo
-- =========================================================
CREATE OR REPLACE VIEW v_rh_executive_summary AS
SELECT
    COUNT(*) AS total_conversations,

    COUNT(*) FILTER (
        WHERE current_stage = 'PROFILE_READY'
    ) AS total_profile_ready,

    COUNT(*) FILTER (
        WHERE requires_human = true
           OR current_stage = 'HUMAN_REVIEW_REQUIRED'
    ) AS total_requires_human,

    COUNT(*) FILTER (
        WHERE risk_level = 'high'
    ) AS total_high_risk,

    COUNT(*) FILTER (
        WHERE current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
    ) AS total_in_progress,

    COUNT(*) FILTER (
        WHERE created_at::date = current_date
    ) AS created_today,

    COUNT(*) FILTER (
        WHERE updated_at::date = current_date
    ) AS updated_today,

    COUNT(DISTINCT channel) AS total_channels

FROM rh_conversations;

COMMIT;
