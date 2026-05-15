-- =========================================================
-- 005_update_work_queue_foraneos.sql
-- Mejora v_rh_work_queue con detección operativa de foráneos
-- Regla:
--   Local = ciudades/zona cercana autorizada de Coahuila/Durango
--   Todo lo demás = foráneo / validar traslado
-- =========================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS unaccent;

DROP VIEW IF EXISTS v_rh_work_queue_summary;
DROP VIEW IF EXISTS v_rh_work_queue;

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
),

base AS (
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

        lower(unaccent(COALESCE(p.ciudad, ''))) AS ciudad_norm,

        now() - COALESCE(c.last_message_at, c.updated_at, c.created_at) AS inactive_time

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
    WHERE c.status IS DISTINCT FROM 'CLOSED'
),

classified AS (
    SELECT
        b.*,

        CASE
            WHEN b.inactive_time >= interval '48 hours'
                THEN 'Inactivo 48h+'
            WHEN b.inactive_time >= interval '24 hours'
                THEN 'Inactivo 24h+'
            WHEN b.inactive_time >= interval '4 hours'
                THEN 'Inactivo 4h+'
            ELSE 'Activo reciente'
        END AS inactivity_bucket,

        CASE
            WHEN b.ciudad IS NOT NULL
             AND b.licencia_federal IS NOT NULL
             AND b.experiencia_quinta_rueda IS NOT NULL
             AND b.apto_medico IS NOT NULL
             AND b.disponibilidad_viajar IS NOT NULL
            THEN true
            ELSE false
        END AS has_basic_profile_complete,

        (
            CASE WHEN b.ciudad IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN b.licencia_federal IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN b.experiencia_quinta_rueda IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN b.apto_medico IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN b.disponibilidad_viajar IS NOT NULL THEN 1 ELSE 0 END
        ) AS completed_basic_fields,

        ROUND(
            (
                (
                    CASE WHEN b.ciudad IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN b.licencia_federal IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN b.experiencia_quinta_rueda IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN b.apto_medico IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN b.disponibilidad_viajar IS NOT NULL THEN 1 ELSE 0 END
                )::numeric / 5::numeric
            ) * 100,
            2
        ) AS profile_completion_pct,

        -- =====================================================
        -- Regla de localidad:
        -- Si está dentro de estas ciudades/apodos, NO es foráneo.
        -- Todo lo demás con ciudad capturada se considera foráneo.
        -- =====================================================
        CASE
            WHEN b.ciudad_norm = '' THEN false

            -- Coahuila: Torreón y alias
            WHEN b.ciudad_norm LIKE '%torreon%' THEN false
            WHEN b.ciudad_norm LIKE '%torreyon%' THEN false
            WHEN b.ciudad_norm LIKE '%chorreon%' THEN false

            -- Coahuila: Matamoros y alias
            WHEN b.ciudad_norm LIKE '%matamoros%' THEN false
            WHEN b.ciudad_norm LIKE '%matachilas%' THEN false

            -- Coahuila: Francisco I. Madero y alias
            WHEN b.ciudad_norm LIKE '%francisco i madero%' THEN false
            WHEN b.ciudad_norm LIKE '%francisco i. madero%' THEN false
            WHEN b.ciudad_norm LIKE '%madero%' THEN false
            WHEN b.ciudad_norm LIKE '%chavez%' THEN false
            WHEN b.ciudad_norm LIKE '%francisco l chavez%' THEN false
            WHEN b.ciudad_norm LIKE '%francisco l. chavez%' THEN false

            -- Coahuila: San Pedro y alias
            WHEN b.ciudad_norm LIKE '%san pedro%' THEN false
            WHEN b.ciudad_norm LIKE '%san peter%' THEN false
            WHEN b.ciudad_norm LIKE '%san pedro de las colonias%' THEN false

            -- Durango: Gómez Palacio y alias
            WHEN b.ciudad_norm LIKE '%gomez palacio%' THEN false
            WHEN b.ciudad_norm LIKE '%gomez%' THEN false

            -- Durango: Lerdo y alias
            WHEN b.ciudad_norm LIKE '%lerdo%' THEN false
            WHEN b.ciudad_norm LIKE '%lerdito%' THEN false
            WHEN b.ciudad_norm LIKE '%ciudad jardin%' THEN false

            -- Durango: Tlahualilo y alias
            WHEN b.ciudad_norm LIKE '%tlahualilo%' THEN false
            WHEN b.ciudad_norm LIKE '%tlahua%' THEN false

            -- Durango: Mapimí y Ojuela
            WHEN b.ciudad_norm LIKE '%mapimi%' THEN false
            WHEN b.ciudad_norm LIKE '%ojuela%' THEN false

            -- Si hay ciudad y no cayó como local, es foráneo.
            WHEN b.ciudad IS NOT NULL AND trim(b.ciudad) <> '' THEN true

            ELSE false
        END AS is_foraneo_candidate,

        CASE
            WHEN b.ciudad_norm = '' THEN NULL

            WHEN b.ciudad_norm LIKE '%torreon%'
              OR b.ciudad_norm LIKE '%torreyon%'
              OR b.ciudad_norm LIKE '%chorreon%'
                THEN 'Local: Torreón'

            WHEN b.ciudad_norm LIKE '%matamoros%'
              OR b.ciudad_norm LIKE '%matachilas%'
                THEN 'Local: Matamoros'

            WHEN b.ciudad_norm LIKE '%francisco i madero%'
              OR b.ciudad_norm LIKE '%francisco i. madero%'
              OR b.ciudad_norm LIKE '%madero%'
              OR b.ciudad_norm LIKE '%chavez%'
              OR b.ciudad_norm LIKE '%francisco l chavez%'
              OR b.ciudad_norm LIKE '%francisco l. chavez%'
                THEN 'Local: Francisco I. Madero'

            WHEN b.ciudad_norm LIKE '%san pedro%'
              OR b.ciudad_norm LIKE '%san peter%'
              OR b.ciudad_norm LIKE '%san pedro de las colonias%'
                THEN 'Local: San Pedro'

            WHEN b.ciudad_norm LIKE '%gomez palacio%'
              OR b.ciudad_norm LIKE '%gomez%'
                THEN 'Local: Gómez Palacio'

            WHEN b.ciudad_norm LIKE '%lerdo%'
              OR b.ciudad_norm LIKE '%lerdito%'
              OR b.ciudad_norm LIKE '%ciudad jardin%'
                THEN 'Local: Lerdo'

            WHEN b.ciudad_norm LIKE '%tlahualilo%'
              OR b.ciudad_norm LIKE '%tlahua%'
                THEN 'Local: Tlahualilo'

            WHEN b.ciudad_norm LIKE '%mapimi%'
              OR b.ciudad_norm LIKE '%ojuela%'
                THEN 'Local: Mapimí'

            WHEN b.ciudad IS NOT NULL AND trim(b.ciudad) <> ''
                THEN 'Foráneo: validar ciudad/base de origen'

            ELSE NULL
        END AS foraneo_reason

    FROM base b
)

SELECT
    c.*,

    CASE
        WHEN c.is_foraneo_candidate = true
         AND c.current_stage = 'PROFILE_READY'
            THEN true
        WHEN c.foraneo_travel_questions > 0
            THEN true
        ELSE false
    END AS needs_travel_validation,

    CASE
        WHEN c.risk_level = 'high'
          OR c.current_stage = 'HUMAN_REVIEW_REQUIRED'
          OR c.open_handoff_count > 0
            THEN 1

        WHEN c.requires_human = true
            THEN 2

        WHEN c.current_stage = 'PROFILE_READY'
          AND (
              c.is_foraneo_candidate = true
              OR c.foraneo_travel_questions > 0
          )
            THEN 3

        WHEN c.current_stage = 'PROFILE_READY'
            THEN 4

        WHEN c.followup_time_questions > 0
          OR c.document_followups > 0
          OR c.foraneo_travel_questions > 0
            THEN 5

        WHEN c.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
            THEN 6

        WHEN c.inactive_time >= interval '24 hours'
          AND c.current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
            THEN 7

        ELSE 8
    END AS work_priority,

    CASE
        WHEN c.risk_level = 'high'
          OR c.current_stage = 'HUMAN_REVIEW_REQUIRED'
          OR c.open_handoff_count > 0
            THEN '1 - Urgente / revisión humana'

        WHEN c.requires_human = true
            THEN '2 - Requiere humano'

        WHEN c.current_stage = 'PROFILE_READY'
          AND (
              c.is_foraneo_candidate = true
              OR c.foraneo_travel_questions > 0
          )
            THEN '3 - Perfil listo foráneo / validar traslado'

        WHEN c.current_stage = 'PROFILE_READY'
            THEN '4 - Perfil listo para RH'

        WHEN c.followup_time_questions > 0
          OR c.document_followups > 0
          OR c.foraneo_travel_questions > 0
            THEN '5 - Seguimiento solicitado'

        WHEN c.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
            THEN '6 - Aclaración pendiente'

        WHEN c.inactive_time >= interval '24 hours'
          AND c.current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
            THEN '7 - Posible abandono'

        ELSE '8 - En proceso normal'
    END AS work_bucket,

    CASE
        WHEN c.risk_level = 'high'
          OR c.current_stage = 'HUMAN_REVIEW_REQUIRED'
          OR c.open_handoff_count > 0
            THEN 'Revisar de inmediato'

        WHEN c.current_stage = 'PROFILE_READY'
          AND (
              c.is_foraneo_candidate = true
              OR c.foraneo_travel_questions > 0
          )
            THEN 'Asignar a Capital Humano y validar traslado / boleto a Torreón si aplica'

        WHEN c.current_stage = 'PROFILE_READY'
            THEN 'Asignar a Capital Humano para revisión'

        WHEN c.foraneo_travel_questions > 0
            THEN 'Validar foráneo / posible apoyo de traslado'

        WHEN c.document_followups > 0
            THEN 'Validar documentación y siguiente paso'

        WHEN c.followup_time_questions > 0
            THEN 'Dar seguimiento por urgencia del candidato'

        WHEN c.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
            THEN 'Esperar aclaración del candidato'

        WHEN c.inactive_time >= interval '24 hours'
          AND c.current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
            THEN 'Reactivar candidato si conviene'

        ELSE 'Continuar flujo automático'
    END AS recommended_action,

    CASE
        WHEN c.risk_level = 'high'
          OR c.current_stage = 'HUMAN_REVIEW_REQUIRED'
            THEN ARRAY['riesgo_alto', 'requiere_humano']

        WHEN c.current_stage = 'PROFILE_READY'
          AND (
              c.is_foraneo_candidate = true
              OR c.foraneo_travel_questions > 0
          )
            THEN ARRAY['perfil_listo', 'requiere_revision_ch', 'foraneo', 'validar_traslado']

        WHEN c.current_stage = 'PROFILE_READY'
            THEN ARRAY['perfil_listo', 'requiere_revision_ch']

        WHEN c.foraneo_travel_questions > 0
            THEN ARRAY['foraneo_boleto', 'validar_traslado']

        WHEN c.document_followups > 0
            THEN ARRAY['documentos', 'seguimiento']

        WHEN c.followup_time_questions > 0
            THEN ARRAY['urgente', 'seguimiento']

        WHEN c.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
            THEN ARRAY['aclaracion_pendiente', 'jerga_ambigua']

        ELSE ARRAY['bot_activo']
    END AS suggested_chatwoot_labels

FROM classified c;


CREATE OR REPLACE VIEW v_rh_work_queue_summary AS
SELECT
    work_priority,
    work_bucket,
    recommended_action,
    COUNT(*) AS total_candidates,
    COUNT(*) FILTER (WHERE risk_level = 'high') AS high_risk_candidates,
    COUNT(*) FILTER (WHERE requires_human = true) AS requires_human_candidates,
    COUNT(*) FILTER (WHERE is_foraneo_candidate = true) AS foraneo_candidates,
    COUNT(*) FILTER (WHERE needs_travel_validation = true) AS travel_validation_candidates,
    MIN(conversation_updated_at) AS oldest_updated_at,
    MAX(conversation_updated_at) AS newest_updated_at
FROM v_rh_work_queue
GROUP BY
    work_priority,
    work_bucket,
    recommended_action
ORDER BY work_priority;

COMMIT;
