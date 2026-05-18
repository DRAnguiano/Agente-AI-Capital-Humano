BEGIN;

DROP VIEW IF EXISTS v_rh_work_queue_summary;
DROP VIEW IF EXISTS v_rh_work_queue;

CREATE OR REPLACE VIEW v_rh_work_queue AS  WITH base AS (
         SELECT c.conversation_key,
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
            COALESCE(p.is_local_laguna, false) AS is_local_laguna,
            COALESCE(p.is_foreign_country, false) AS is_foreign_country,
            COALESCE(p.location_requires_ch_validation, false) AS location_requires_ch_validation,
            COALESCE(p.location_needs_travel_validation, false) AS location_needs_travel_validation,
            p.city_catalog_alias,
            p.city_catalog_id,
            p.licencia_federal,
            p.tipo_licencia,
            p.experiencia_quinta_rueda,
            p.apto_medico,
            p.disponibilidad_viajar,
            p.perfil_status,
            p.observaciones,
            EXTRACT(epoch FROM now() - c.updated_at) / 3600.0 AS inactive_hours
           FROM rh_conversations c
             LEFT JOIN rh_candidate_profile p ON p.conversation_key = c.conversation_key
        ), classified AS (
         SELECT base.conversation_key,
            base.channel,
            base.channel_user_id,
            base.current_stage,
            base.last_intent,
            base.risk_level,
            base.requires_human,
            base.conversation_updated_at,
            base.last_message_at,
            base.nombre_completo,
            base.telefono,
            base.ciudad,
            base.ciudad_raw,
            base.estado_region,
            base.pais_codigo,
            base.pais_nombre,
            base.city_group,
            base.is_local_laguna,
            base.is_foreign_country,
            base.location_requires_ch_validation,
            base.location_needs_travel_validation,
            base.city_catalog_alias,
            base.city_catalog_id,
            base.licencia_federal,
            base.tipo_licencia,
            base.experiencia_quinta_rueda,
            base.apto_medico,
            base.disponibilidad_viajar,
            base.perfil_status,
            base.observaciones,
            base.inactive_hours,
                CASE
                    WHEN base.current_stage = 'HUMAN_REVIEW_REQUIRED'::text OR base.risk_level = 'high'::text OR base.requires_human = true AND base.risk_level = 'high'::text THEN 1
                    WHEN base.is_foreign_country = true OR base.location_requires_ch_validation = true OR base.pais_codigo IS NOT NULL AND base.pais_codigo <> 'MX'::text THEN 2
                    WHEN base.current_stage = 'PROFILE_READY'::text AND base.location_needs_travel_validation = true AND base.is_local_laguna = false AND base.is_foreign_country = false THEN 3
                    WHEN base.current_stage = 'PROFILE_READY'::text AND base.is_local_laguna = true THEN 4
                    WHEN base.current_stage = 'PROFILE_READY'::text THEN 5
                    WHEN base.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'::text THEN 6
                    WHEN (base.current_stage <> ALL (ARRAY['PROFILE_READY'::text, 'HUMAN_REVIEW_REQUIRED'::text])) AND base.inactive_hours >= 24::numeric THEN 7
                    ELSE 8
                END AS work_priority,
                CASE
                    WHEN base.current_stage = 'HUMAN_REVIEW_REQUIRED'::text OR base.risk_level = 'high'::text OR base.requires_human = true AND base.risk_level = 'high'::text THEN '1 - Urgente / revisión humana'::text
                    WHEN base.is_foreign_country = true OR base.location_requires_ch_validation = true OR base.pais_codigo IS NOT NULL AND base.pais_codigo <> 'MX'::text THEN '2 - Ubicación extranjera / validar C.H.'::text
                    WHEN base.current_stage = 'PROFILE_READY'::text AND base.location_needs_travel_validation = true AND base.is_local_laguna = false AND base.is_foreign_country = false THEN '3 - Perfil listo foráneo / validar traslado'::text
                    WHEN base.current_stage = 'PROFILE_READY'::text AND base.is_local_laguna = true THEN '4 - Perfil listo local'::text
                    WHEN base.current_stage = 'PROFILE_READY'::text THEN '5 - Perfil listo para RH'::text
                    WHEN base.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'::text THEN '6 - Aclaración pendiente'::text
                    WHEN (base.current_stage <> ALL (ARRAY['PROFILE_READY'::text, 'HUMAN_REVIEW_REQUIRED'::text])) AND base.inactive_hours >= 24::numeric THEN '7 - Posible abandono'::text
                    ELSE '8 - En proceso normal'::text
                END AS work_bucket,
                CASE
                    WHEN base.current_stage = 'HUMAN_REVIEW_REQUIRED'::text OR base.risk_level = 'high'::text OR base.requires_human = true AND base.risk_level = 'high'::text THEN 'Revisar de inmediato'::text
                    WHEN base.is_foreign_country = true OR base.location_requires_ch_validation = true OR base.pais_codigo IS NOT NULL AND base.pais_codigo <> 'MX'::text THEN 'Validar ubicación con Capital Humano antes de continuar'::text
                    WHEN base.current_stage = 'PROFILE_READY'::text AND base.location_needs_travel_validation = true AND base.is_local_laguna = false AND base.is_foreign_country = false THEN 'Asignar a Capital Humano y validar traslado / boleto a Torreón si aplica'::text
                    WHEN base.current_stage = 'PROFILE_READY'::text AND base.is_local_laguna = true THEN 'Asignar a Capital Humano para revisión local'::text
                    WHEN base.current_stage = 'PROFILE_READY'::text THEN 'Asignar a Capital Humano para revisión'::text
                    WHEN base.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'::text THEN 'Esperar aclaración del candidato'::text
                    WHEN (base.current_stage <> ALL (ARRAY['PROFILE_READY'::text, 'HUMAN_REVIEW_REQUIRED'::text])) AND base.inactive_hours >= 24::numeric THEN 'Reactivar candidato si conviene'::text
                    ELSE 'Continuar flujo automático'::text
                END AS recommended_action,
                CASE
                    WHEN base.current_stage = 'HUMAN_REVIEW_REQUIRED'::text OR base.risk_level = 'high'::text OR base.requires_human = true AND base.risk_level = 'high'::text THEN ARRAY['riesgo_alto'::text, 'requiere_humano'::text]
                    WHEN base.is_foreign_country = true OR base.location_requires_ch_validation = true OR base.pais_codigo IS NOT NULL AND base.pais_codigo <> 'MX'::text THEN
                    CASE
                        WHEN base.current_stage = 'PROFILE_READY'::text THEN ARRAY['perfil_listo'::text, 'requiere_revision_ch'::text, 'ubicacion_extranjero'::text, 'validar_ch'::text]
                        ELSE ARRAY['requiere_revision_ch'::text, 'ubicacion_extranjero'::text, 'validar_ch'::text]
                    END
                    WHEN base.current_stage = 'PROFILE_READY'::text AND base.location_needs_travel_validation = true AND base.is_local_laguna = false AND base.is_foreign_country = false THEN ARRAY['perfil_listo'::text, 'requiere_revision_ch'::text, 'foraneo'::text, 'validar_traslado'::text]
                    WHEN base.current_stage = 'PROFILE_READY'::text AND base.is_local_laguna = true THEN ARRAY['perfil_listo'::text, 'requiere_revision_ch'::text, 'local_laguna'::text]
                    WHEN base.current_stage = 'PROFILE_READY'::text THEN ARRAY['perfil_listo'::text, 'requiere_revision_ch'::text]
                    WHEN base.current_stage = 'CLARIFY_AMBIGUOUS_SLANG'::text THEN ARRAY['aclaracion_pendiente'::text, 'jerga_ambigua'::text]
                    WHEN (base.current_stage <> ALL (ARRAY['PROFILE_READY'::text, 'HUMAN_REVIEW_REQUIRED'::text])) AND base.inactive_hours >= 24::numeric THEN ARRAY['bot_activo'::text, 'posible_abandono'::text]
                    ELSE ARRAY['bot_activo'::text]
                END AS suggested_chatwoot_labels
           FROM base
        )
 SELECT work_priority,
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
    suggested_chatwoot_labels,
    inactive_hours,
    last_message_at,
    conversation_updated_at
   FROM classified;;

CREATE OR REPLACE VIEW v_rh_work_queue_summary AS  SELECT work_priority,
    work_bucket,
    recommended_action,
    count(*) AS total_candidates,
    count(*) FILTER (WHERE risk_level = 'high'::text) AS high_risk_candidates,
    count(*) FILTER (WHERE requires_human = true) AS requires_human_candidates,
    count(*) FILTER (WHERE is_foreign_country = true) AS foreign_country_candidates,
    count(*) FILTER (WHERE location_requires_ch_validation = true) AS location_validation_candidates,
    count(*) FILTER (WHERE location_needs_travel_validation = true AND is_foreign_country = false AND is_local_laguna = false) AS travel_validation_candidates,
    min(conversation_updated_at) AS oldest_updated_at,
    max(conversation_updated_at) AS newest_updated_at
   FROM v_rh_work_queue
  GROUP BY work_priority, work_bucket, recommended_action;;

COMMIT;
