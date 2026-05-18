BEGIN;

DROP VIEW IF EXISTS v_rh_work_queue_summary;
DROP VIEW IF EXISTS v_rh_work_queue;

CREATE OR REPLACE VIEW v_rh_work_queue AS
WITH base AS (
    SELECT
        c.conversation_key,
        c.channel,
        c.channel_user_id,
        c.current_stage,
        c.last_intent,
        c.risk_level,
        c.requires_human,
        c.updated_at AS conversation_updated_at,
        c.last_message_at,

        p.nombre_completo,
        p.telefono,

        p.ciudad,
        p.ciudad_raw,
        p.estado_region,
        p.pais_codigo,
        p.pais_nombre,
        p.city_group,
        COALESCE(p.is_local_laguna, FALSE) AS is_local_laguna,
        COALESCE(p.is_foreign_country, FALSE) AS is_foreign_country,
        COALESCE(p.location_requires_ch_validation, FALSE) AS location_requires_ch_validation,
        COALESCE(p.location_needs_travel_validation, FALSE) AS location_needs_travel_validation,
        p.city_catalog_alias,
        p.city_catalog_id,

        p.licencia_federal,
        p.tipo_licencia,
        p.experiencia_quinta_rueda,
        p.apto_medico,
        p.disponibilidad_viajar,
        p.perfil_status,
        p.observaciones,

        EXTRACT(EPOCH FROM (now() - c.updated_at)) / 3600.0 AS inactive_hours
    FROM rh_conversations c
    LEFT JOIN rh_candidate_profile p
        ON p.conversation_key = c.conversation_key
),
flags AS (
    SELECT
        *,

        (
            current_stage = 'PROFILE_READY'
        ) AS is_profile_ready,

        (
            ciudad IS NOT NULL
            AND licencia_federal IS NOT NULL
            AND experiencia_quinta_rueda IS NOT NULL
            AND apto_medico IS NOT NULL
            AND disponibilidad_viajar IS NOT NULL
        ) AS has_base_profile_data,

        (
            risk_level = 'high'
            OR last_intent IN (
                'sensitive_handoff',
                'rcontrol_or_incident_handoff',
                'slang_clarification_risky'
            )
        ) AS is_restrictive_review,

        (
            is_foreign_country = TRUE
            OR location_requires_ch_validation = TRUE
            OR (pais_codigo IS NOT NULL AND pais_codigo <> 'MX')
        ) AS needs_location_ch_validation,

        (
            location_needs_travel_validation = TRUE
            AND is_local_laguna = FALSE
            AND is_foreign_country = FALSE
            AND COALESCE(pais_codigo, 'MX') = 'MX'
        ) AS is_foraneo_mx

    FROM base
),
classified AS (
    SELECT
        *,

        CASE
            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND is_local_laguna = TRUE
                THEN 1

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND is_foraneo_mx = TRUE
                THEN 2

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND needs_location_ch_validation = TRUE
                THEN 3

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                THEN 4

            WHEN current_stage NOT IN (
                    'PROFILE_READY',
                    'HUMAN_REVIEW_REQUIRED',
                    'CLARIFY_AMBIGUOUS_SLANG'
                 )
                 AND inactive_hours < 24
                 AND is_restrictive_review = FALSE
                THEN 5

            WHEN current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
                 AND is_restrictive_review = FALSE
                THEN 6

            WHEN current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
                 AND inactive_hours >= 24
                 AND is_restrictive_review = FALSE
                THEN 7

            WHEN is_restrictive_review = TRUE
                THEN 8

            ELSE 5
        END AS work_priority,

        CASE
            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND is_local_laguna = TRUE
                THEN '1 - Perfil listo local / validar RH'

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND is_foraneo_mx = TRUE
                THEN '2 - Perfil listo foráneo / validar traslado'

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND needs_location_ch_validation = TRUE
                THEN '3 - Perfil listo ubicación extranjera / validar CH'

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                THEN '4 - Perfil listo con dato pendiente de validación'

            WHEN current_stage NOT IN (
                    'PROFILE_READY',
                    'HUMAN_REVIEW_REQUIRED',
                    'CLARIFY_AMBIGUOUS_SLANG'
                 )
                 AND inactive_hours < 24
                 AND is_restrictive_review = FALSE
                THEN '5 - En proceso normal'

            WHEN current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
                 AND is_restrictive_review = FALSE
                THEN '6 - Aclaración pendiente'

            WHEN current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
                 AND inactive_hours >= 24
                 AND is_restrictive_review = FALSE
                THEN '7 - Posible abandono'

            WHEN is_restrictive_review = TRUE
                THEN '8 - Revisión restrictiva / posible no apto'

            ELSE '5 - En proceso normal'
        END AS work_bucket,

        CASE
            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND is_local_laguna = TRUE
                THEN 'Asignar a Capital Humano para validación local'

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND is_foraneo_mx = TRUE
                THEN 'Asignar a Capital Humano y validar traslado / boleto a Torreón si aplica'

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND needs_location_ch_validation = TRUE
                THEN 'Asignar a Capital Humano y validar ubicación antes de continuar'

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                THEN 'Asignar a Capital Humano para validar dato pendiente'

            WHEN current_stage NOT IN (
                    'PROFILE_READY',
                    'HUMAN_REVIEW_REQUIRED',
                    'CLARIFY_AMBIGUOUS_SLANG'
                 )
                 AND inactive_hours < 24
                 AND is_restrictive_review = FALSE
                THEN 'Continuar flujo automático'

            WHEN current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
                 AND is_restrictive_review = FALSE
                THEN 'Esperar aclaración del candidato'

            WHEN current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
                 AND inactive_hours >= 24
                 AND is_restrictive_review = FALSE
                THEN 'Reactivar candidato si conviene'

            WHEN is_restrictive_review = TRUE
                THEN 'Enviar a revisión restrictiva; no priorizar como lead viable hasta validación CH'

            ELSE 'Continuar flujo automático'
        END AS recommended_action,

        CASE
            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND is_local_laguna = TRUE
                THEN ARRAY['perfil_listo', 'requiere_revision_ch', 'local_laguna']

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND is_foraneo_mx = TRUE
                THEN ARRAY['perfil_listo', 'requiere_revision_ch', 'foraneo', 'validar_traslado']

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                 AND needs_location_ch_validation = TRUE
                THEN ARRAY['perfil_listo', 'requiere_revision_ch', 'ubicacion_extranjero', 'validar_ch']

            WHEN is_profile_ready = TRUE
                 AND is_restrictive_review = FALSE
                THEN ARRAY['perfil_listo', 'requiere_revision_ch', 'validar_dato_pendiente']

            WHEN current_stage NOT IN (
                    'PROFILE_READY',
                    'HUMAN_REVIEW_REQUIRED',
                    'CLARIFY_AMBIGUOUS_SLANG'
                 )
                 AND inactive_hours < 24
                 AND is_restrictive_review = FALSE
                THEN ARRAY['bot_activo']

            WHEN current_stage = 'CLARIFY_AMBIGUOUS_SLANG'
                 AND is_restrictive_review = FALSE
                THEN ARRAY['aclaracion_pendiente', 'jerga_ambigua']

            WHEN current_stage NOT IN ('PROFILE_READY', 'HUMAN_REVIEW_REQUIRED')
                 AND inactive_hours >= 24
                 AND is_restrictive_review = FALSE
                THEN ARRAY['bot_activo', 'posible_abandono']

            WHEN is_restrictive_review = TRUE
                THEN ARRAY['revision_restrictiva', 'posible_no_apto', 'requiere_humano']

            ELSE ARRAY['bot_activo']
        END AS suggested_chatwoot_labels

    FROM flags
)
SELECT
    work_priority,
    work_bucket,
    recommended_action,

    conversation_key,
    channel,
    channel_user_id,
    current_stage,
    last_intent,

    nombre_completo,
    telefono,

    ciudad,
    ciudad_raw,
    estado_region,
    pais_codigo,
    pais_nombre,
    city_group,
    is_local_laguna,
    is_foreign_country,
    location_requires_ch_validation,
    location_needs_travel_validation,
    city_catalog_alias,
    city_catalog_id,

    licencia_federal,
    tipo_licencia,
    experiencia_quinta_rueda,
    apto_medico,
    disponibilidad_viajar,

    risk_level,
    requires_human,
    perfil_status,
    observaciones,

    is_profile_ready,
    has_base_profile_data,
    is_restrictive_review,
    needs_location_ch_validation,
    is_foraneo_mx,

    suggested_chatwoot_labels,
    inactive_hours,
    last_message_at,
    conversation_updated_at
FROM classified;

CREATE OR REPLACE VIEW v_rh_work_queue_summary AS
SELECT
    work_priority,
    work_bucket,
    recommended_action,
    COUNT(*) AS total_candidates,

    COUNT(*) FILTER (WHERE is_profile_ready = TRUE) AS profile_ready_candidates,
    COUNT(*) FILTER (WHERE has_base_profile_data = TRUE) AS with_base_profile_data,
    COUNT(*) FILTER (WHERE is_restrictive_review = TRUE) AS restrictive_review_candidates,
    COUNT(*) FILTER (WHERE is_foreign_country = TRUE) AS foreign_country_candidates,
    COUNT(*) FILTER (WHERE is_foraneo_mx = TRUE) AS foraneo_mx_candidates,
    COUNT(*) FILTER (WHERE is_local_laguna = TRUE) AS local_laguna_candidates,
    COUNT(*) FILTER (WHERE requires_human = TRUE) AS requires_human_candidates,

    MIN(conversation_updated_at) AS oldest_updated_at,
    MAX(conversation_updated_at) AS newest_updated_at
FROM v_rh_work_queue
GROUP BY
    work_priority,
    work_bucket,
    recommended_action;

COMMIT;
