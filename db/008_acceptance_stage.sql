BEGIN;

CREATE OR REPLACE FUNCTION rh_lead_v2_effective_stage(p_lead_key TEXT, p_current_stage TEXT)
RETURNS TEXT AS $$
DECLARE
    has_apto_pending BOOLEAN;
    has_docs_pending_send BOOLEAN;
    has_vacancy_accepted BOOLEAN;
    has_city BOOLEAN;
    has_license_category BOOLEAN;
    has_license_status BOOLEAN;
    has_apto_status BOOLEAN;
    has_experience BOOLEAN;
    is_viable_profile BOOLEAN;
BEGIN
    IF COALESCE(p_current_stage, 'new') IN ('human_review', 'lost', 'closed') THEN
        RETURN p_current_stage;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM rh_lead_facts_v2 f
        WHERE f.lead_key = p_lead_key AND f.is_active = true
          AND f.fact_group IN ('document', 'medical')
          AND f.fact_key IN ('apto_status', 'apto_expires_in')
          AND f.fact_value IN ('expires_in_2_months', 'pending_update', 'expired', 'vencido')
    ) INTO has_apto_pending;

    IF has_apto_pending THEN
        RETURN 'apto_pending_update';
    END IF;

    SELECT
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'documents' AND f.fact_key = 'submission_status' AND f.fact_value = 'pending_candidate_will_send'),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'candidate' AND f.fact_key = 'vacancy_accepted' AND f.fact_value = 'sí'),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'candidate' AND f.fact_key = 'city'),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'license' AND f.fact_key = 'category'),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'license' AND f.fact_key IN ('status', 'expires_in', 'expires_at')),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'medical' AND f.fact_key IN ('apto_status', 'apto_expires_in', 'apto_expires_at')),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'experience' AND f.fact_key IN ('fifth_wheel', 'years'))
    INTO has_docs_pending_send, has_vacancy_accepted, has_city, has_license_category, has_license_status, has_apto_status, has_experience;

    is_viable_profile := has_city AND has_license_category AND has_apto_status AND has_experience;

    IF is_viable_profile AND has_vacancy_accepted THEN
        RETURN 'potential_candidate_documents_pending';
    END IF;

    IF has_docs_pending_send THEN
        RETURN 'potential_candidate_documents_pending';
    END IF;

    IF is_viable_profile THEN
        RETURN 'profiled_viable';
    END IF;

    IF has_city OR has_license_category OR has_license_status OR has_apto_status OR has_experience THEN
        RETURN 'profile_in_progress';
    END IF;

    RETURN COALESCE(p_current_stage, 'new');
END;
$$ LANGUAGE plpgsql STABLE;

DROP VIEW IF EXISTS v_rh_lead_memory_v2;

CREATE VIEW v_rh_lead_memory_v2 AS
WITH lead_effective AS (
    SELECT
        l.*,
        rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) AS effective_funnel_stage,
        CASE
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'apto_pending_update'
                THEN 'Dar seguimiento cuando el candidato actualice apto médico.'
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'profile_in_progress'
                THEN 'Continuar perfilamiento con una sola pregunta útil por turno.'
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'profiled_viable'
                THEN 'Confirmar si la vacante le agradó para avanzar a envío documental.'
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'potential_candidate_documents_pending'
                THEN 'Esperar documentación prometida y pasar a validación de Capital Humano cuando la comparta.'
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'potential_candidate_documents_sent'
                THEN 'Capital Humano debe validar documentación del candidato potencial.'
            ELSE l.next_best_action
        END AS effective_next_best_action,
        CASE
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'apto_pending_update'
                THEN 'El candidato mencionó que su apto médico está vencido o próximo a vencer.'
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'profile_in_progress'
                THEN 'El candidato compartió datos iniciales para perfilamiento.'
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'profiled_viable'
                THEN 'El candidato parece viable por perfil inicial; falta confirmar aceptación y documentación.'
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'potential_candidate_documents_pending'
                THEN 'El candidato aceptó o mostró interés en avanzar; queda pendiente que comparta documentación para revisión.'
            WHEN rh_lead_v2_effective_stage(l.lead_key, l.funnel_stage) = 'potential_candidate_documents_sent'
                THEN 'El candidato indica que ya compartió documentación; Capital Humano debe validarla.'
            ELSE l.memory_summary
        END AS effective_memory_summary
    FROM rh_leads_v2 l
), facts_agg AS (
    SELECT
        f.lead_key,
        jsonb_object_agg(f.fact_group || '.' || f.fact_key, f.fact_value) AS active_facts,
        jsonb_object_agg(rh_lead_fact_label_es(f.fact_group, f.fact_key), rh_lead_fact_value_es(f.fact_group, f.fact_key, f.fact_value)) AS active_facts_es,
        string_agg('• ' || rh_lead_fact_label_es(f.fact_group, f.fact_key) || ': ' || rh_lead_fact_value_es(f.fact_group, f.fact_key, f.fact_value), E'\n' ORDER BY f.updated_at DESC) AS active_facts_text
    FROM rh_lead_facts_v2 f
    WHERE f.is_active = true
    GROUP BY f.lead_key
)
SELECT
    l.lead_key, l.display_name, l.phone, l.source_channel, l.lead_status,
    l.effective_funnel_stage AS funnel_stage,
    c.stage_label AS funnel_stage_label,
    c.stage_order AS funnel_stage_order,
    l.effective_next_best_action AS next_best_action,
    l.effective_memory_summary AS memory_summary,
    l.facts_summary, l.risk_level,
    CASE WHEN l.effective_funnel_stage IN ('potential_candidate_documents_pending', 'potential_candidate_documents_sent') THEN true ELSE l.requires_human END AS requires_human,
    l.first_seen_at, l.last_seen_at, l.updated_at,
    fa.active_facts, fa.active_facts_es, fa.active_facts_text,
    (
        SELECT jsonb_agg(jsonb_build_object('event_type', e.event_type, 'intent', e.intent, 'route', e.route, 'stage_to', e.stage_to, 'created_at', e.created_at) ORDER BY e.created_at DESC)
        FROM (
            SELECT * FROM rh_lead_events_v2 e
            WHERE e.lead_key = l.lead_key
            ORDER BY e.created_at DESC
            LIMIT 10
        ) e
    ) AS recent_events
FROM lead_effective l
LEFT JOIN rh_funnel_stage_catalog_v2 c ON c.stage_key = l.effective_funnel_stage
LEFT JOIN facts_agg fa ON fa.lead_key = l.lead_key;

COMMIT;
