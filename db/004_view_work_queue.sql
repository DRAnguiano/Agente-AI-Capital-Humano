-- =========================================================
-- 004_view_work_queue.sql
-- Vista operativa para priorizar candidatos en Capital Humano
-- Proyecto: Agente RH Operadores Quinta Rueda
-- =========================================================

BEGIN;

CREATE OR REPLACE VIEW v_rh_work_queue AS
WITH last_user_message AS (
    SELECT DISTINCT ON (conversation_key)
        conversation_key,
        message AS last_candidate_message,
        created_at AS last_candidate_message_at
    FROM rh_messages
    WHERE role IN ('user', 'candidate')
    ORDER BY conversation_key, created_at DESC
),

last_bot_message AS (
    SELECT DISTINCT ON (conversation_key)
        conversation_key,
        message AS last_bot_message,
        created_at AS last_bot_message_at
    FROM rh_messages
    WHERE role IN ('assistant', 'bot')
    ORDER BY conversation_key, created_at DESC
),

open_handoffs AS (
    SELECT
        conversation_key,
        COUNT(*) AS open_handoff_count,
        MAX(created_at) AS last_handoff_at,
        STRING_AGG(DISTINCT reason, ', ') AS handoff_reasons
    FROM rh_human_handoffs
    WHERE status IN ('OPEN', 'IN_PROGRESS')
    GROUP BY conversation_key
),

event_summary AS (
    SELECT
        conversation_key,
        COUNT(*) AS total_events,
        COUNT(*) FILTER (WHERE event_type = 'rag_answered') AS rag_answers,
        COUNT(*) FILTER (WHERE event_type = 'human_handoff_created') AS handoffs_created,
        COUNT(*) FILTER (WHERE event_type = 'clarification_requested') AS clarifications_requested,
        COUNT(*) FILTER (WHERE intent = 'followup_time_question') AS followup_time_questions,
        COUNT(*) FILTER (WHERE intent = 'documents_complete_followup') AS document_followups,
        COUNT(*) FILTER (WHERE intent = 'foraneo_travel_question') AS foraneo_travel_questions,
        MAX(created_at) AS last_event_at
    FROM rh_candidate_events
    GROUP BY conversation_key
)

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

    p.nombre_completo,
    p.edad,
    p.ciudad,
    p.telefono,
    p.experiencia_quinta_rueda,
    p.licencia_federal,
    p.tipo_licencia,
    p.apto_medico,
    p.disponibilidad_viajar,
    p.documentos,
    p.perfil_status,
    p.score,
    p.observaciones,
    p.source,
    p.vacancy,

    lum.last_candidate_message,
    lum.last_candidate_message_at,
    lbm.last_bot_message,
    lbm.last_bot_message_at,

    COALESCE(oh.open_handoff_count, 0) AS open_handoff_count,
    oh.last_handoff_at,
    oh.handoff_reasons,

    COALESCE(es.total_events, 0) AS total_events,
    COALESCE(es.rag_answers, 0) AS rag_answers,
    COALESCE(es.handoffs_created, 0) AS handoffs_created,
    COALESCE(es.clarifications_requested, 0) AS clarifications_requested,
    COALESCE(es.followup_time_questions, 0) AS followup_time_questions,
    COALESCE(es.document_followups, 0) AS document_followups,
    COALESCE(es.foraneo_travel_questions, 0) AS foraneo_travel_questions,
    es.last_event_at,

    now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) AS inactive_time,

    CASE
        WHEN now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) >= interval '48 hours'
            THEN 'Inactivo 48h+'
        WHEN now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) >= interval '24 hours'
            THEN 'Inactivo 24h+'
        WHEN now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) >= interval '4 hours'
            THEN 'Inactivo 4h+'
        ELSE 'Activo reciente'
    END AS inactivity_bucket,

    CASE
        WHEN p.ciudad IS NOT NULL
         AND p.licencia_federal IS NOT NULL
         AND p.experiencia_quinta_rueda IS NOT NULL
         AND p.apto_medico IS NOT NULL
         AND p.disponibilidad_viajar IS NOT NULL
        THEN true
        ELSE false
    END AS has_basic_profile_complete,

    (
        CASE WHEN p.ciudad IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN p.licencia_federal IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN p.experiencia_quinta_rueda IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN p.apto_medico IS NOT NULL THEN 1 ELSE 0 END +
        CASE WHEN p.disponibilidad_viajar IS NOT NULL THEN 1 ELSE 0 END
    ) AS completed_basic_fields,

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
        WHEN c.risk_level = 'high'
          OR c.current_stage = 'HUMAN_REVIEW_REQUIRED'
          OR COALESCE(oh.open_handoff_count, 0) > 0
            THEN 1

        WHEN c.requires_human = true
            THEN 2

        WHEN c.current_stage = 'PROFILE_READY'
            THEN 3

        WHEN COALESCE(es.followup_time_questions, 0) > 0
          OR COALESCE(es.document_followups, 0) > 0
          OR COALESCE(es.foraneo_travel_questions, 0) > 0
            THEN 4

        WHEN c.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
            THEN 5

        WHEN now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) >= interval '24 hours'
          AND c.current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
            THEN 6

        ELSE 7
    END AS work_priority,

    CASE
        WHEN c.risk_level = 'high'
          OR c.current_stage = 'HUMAN_REVIEW_REQUIRED'
          OR COALESCE(oh.open_handoff_count, 0) > 0
            THEN '1 - Urgente / revisión humana'

        WHEN c.requires_human = true
            THEN '2 - Requiere humano'

        WHEN c.current_stage = 'PROFILE_READY'
            THEN '3 - Perfil listo para RH'

        WHEN COALESCE(es.followup_time_questions, 0) > 0
          OR COALESCE(es.document_followups, 0) > 0
          OR COALESCE(es.foraneo_travel_questions, 0) > 0
            THEN '4 - Seguimiento solicitado'

        WHEN c.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
            THEN '5 - Aclaración pendiente'

        WHEN now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) >= interval '24 hours'
          AND c.current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
            THEN '6 - Posible abandono'

        ELSE '7 - En proceso normal'
    END AS work_bucket,

    CASE
        WHEN c.risk_level = 'high'
          OR c.current_stage = 'HUMAN_REVIEW_REQUIRED'
          OR COALESCE(oh.open_handoff_count, 0) > 0
            THEN 'Revisar de inmediato'

        WHEN c.current_stage = 'PROFILE_READY'
            THEN 'Asignar a Capital Humano para revisión'

        WHEN COALESCE(es.foraneo_travel_questions, 0) > 0
            THEN 'Validar foráneo / posible apoyo de traslado'

        WHEN COALESCE(es.document_followups, 0) > 0
            THEN 'Validar documentación y siguiente paso'

        WHEN COALESCE(es.followup_time_questions, 0) > 0
            THEN 'Dar seguimiento por urgencia del candidato'

        WHEN c.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
            THEN 'Esperar aclaración del candidato'

        WHEN now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) >= interval '24 hours'
          AND c.current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
            THEN 'Reactivar candidato si conviene'

        ELSE 'Continuar flujo automático'
    END AS recommended_action,

    CASE
        WHEN c.risk_level = 'high'
          OR c.current_stage = 'HUMAN_REVIEW_REQUIRED'
            THEN ARRAY['riesgo_alto', 'requiere_humano']

        WHEN c.current_stage = 'PROFILE_READY'
            THEN ARRAY['perfil_listo', 'requiere_revision_ch']

        WHEN COALESCE(es.foraneo_travel_questions, 0) > 0
            THEN ARRAY['foraneo_boleto', 'validar_traslado']

        WHEN COALESCE(es.document_followups, 0) > 0
            THEN ARRAY['documentos', 'seguimiento']

        WHEN COALESCE(es.followup_time_questions, 0) > 0
            THEN ARRAY['urgente', 'seguimiento']

        WHEN c.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
            THEN ARRAY['aclaracion_pendiente', 'jerga_ambigua']

        ELSE ARRAY['bot_activo']
    END AS suggested_chatwoot_labels

FROM rh_conversations c
LEFT JOIN rh_candidate_profile p
    ON p.conversation_key = c.conversation_key
LEFT JOIN last_user_message lum
    ON lum.conversation_key = c.conversation_key
LEFT JOIN last_bot_message lbm
    ON lbm.conversation_key = c.conversation_key
LEFT JOIN open_handoffs oh
    ON oh.conversation_key = c.conversation_key
LEFT JOIN event_summary es
    ON es.conversation_key = c.conversation_key
WHERE c.status IS DISTINCT FROM 'CLOSED';


-- =========================================================
-- Resumen de cola de trabajo
-- =========================================================
CREATE OR REPLACE VIEW v_rh_work_queue_summary AS
SELECT
    work_priority,
    work_bucket,
    recommended_action,
    COUNT(*) AS total_candidates,
    COUNT(*) FILTER (WHERE risk_level = 'high') AS high_risk_candidates,
    COUNT(*) FILTER (WHERE requires_human = true) AS requires_human_candidates,
    MIN(conversation_updated_at) AS oldest_updated_at,
    MAX(conversation_updated_at) AS newest_updated_at
FROM v_rh_work_queue
GROUP BY
    work_priority,
    work_bucket,
    recommended_action
ORDER BY work_priority;

COMMIT;
