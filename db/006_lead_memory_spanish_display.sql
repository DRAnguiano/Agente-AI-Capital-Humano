-- =========================================================
-- 006_lead_memory_spanish_display.sql
-- Campos amigables en español para RH / Power BI / notas internas.
--
-- La memoria técnica puede seguir usando llaves estables como:
-- role_fit.operator_type, document.apto_status, interest.payment
--
-- Pero la vista expone también:
-- - active_facts_es: JSON con etiquetas legibles
-- - active_facts_text: texto listo para nota interna
--
-- Esto evita mostrar guiones bajos o llaves técnicas a RH.
-- =========================================================

BEGIN;

CREATE OR REPLACE FUNCTION rh_lead_fact_label_es(p_fact_group TEXT, p_fact_key TEXT)
RETURNS TEXT AS $$
DECLARE
    k TEXT := COALESCE(p_fact_group, '') || '.' || COALESCE(p_fact_key, '');
BEGIN
    RETURN CASE k
        WHEN 'role_fit.operator_type' THEN 'Tipo de operador'
        WHEN 'document.apto_status' THEN 'Apto médico'
        WHEN 'documents.submission_status' THEN 'Documentos'
        WHEN 'interest.payment' THEN 'Interés en pago'
        WHEN 'interest.requirements_documents' THEN 'Interés en requisitos'
        ELSE initcap(replace(replace(k, '_', ' '), '.', ' / '))
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION rh_lead_fact_value_es(p_fact_group TEXT, p_fact_key TEXT, p_fact_value TEXT)
RETURNS TEXT AS $$
DECLARE
    k TEXT := COALESCE(p_fact_group, '') || '.' || COALESCE(p_fact_key, '');
    v TEXT := COALESCE(p_fact_value, '');
BEGIN
    RETURN CASE
        WHEN k = 'role_fit.operator_type' AND v = 'operador_5ta_rueda'
            THEN 'Operador de quinta rueda'
        WHEN k = 'document.apto_status' AND v = 'expires_in_2_months'
            THEN 'Vence en 2 meses'
        WHEN k = 'document.apto_status' AND v = 'pending_update'
            THEN 'Pendiente de actualizar'
        WHEN k = 'document.apto_status' AND v = 'expired'
            THEN 'Vencido'
        WHEN k = 'documents.submission_status' AND v = 'candidate_says_sent'
            THEN 'El candidato indica que ya los envió'
        WHEN k = 'interest.payment' AND v = 'asked'
            THEN 'Preguntó por pago'
        WHEN k = 'interest.requirements_documents' AND v = 'asked'
            THEN 'Preguntó por requisitos/documentos'
        ELSE initcap(replace(v, '_', ' '))
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE VIEW v_rh_lead_memory_v2 AS
WITH lead_effective AS (
    SELECT
        l.*,
        rh_lead_v2_has_apto_pending(l.lead_key) AS has_apto_pending,
        CASE
            WHEN rh_lead_v2_has_apto_pending(l.lead_key)
                 AND COALESCE(l.funnel_stage, 'new') NOT IN ('human_review', 'lost', 'closed')
            THEN 'apto_pending_update'
            ELSE l.funnel_stage
        END AS effective_funnel_stage,
        CASE
            WHEN rh_lead_v2_has_apto_pending(l.lead_key)
                 AND COALESCE(l.funnel_stage, 'new') NOT IN ('human_review', 'lost', 'closed')
            THEN 'Dar seguimiento cuando el candidato actualice apto médico.'
            ELSE l.next_best_action
        END AS effective_next_best_action,
        CASE
            WHEN rh_lead_v2_has_apto_pending(l.lead_key)
                 AND COALESCE(l.funnel_stage, 'new') NOT IN ('human_review', 'lost', 'closed')
            THEN 'El candidato mencionó que su apto médico está vencido o próximo a vencer.'
            ELSE l.memory_summary
        END AS effective_memory_summary
    FROM rh_leads_v2 l
), facts_agg AS (
    SELECT
        f.lead_key,
        jsonb_object_agg(f.fact_group || '.' || f.fact_key, f.fact_value) AS active_facts,
        jsonb_object_agg(
            rh_lead_fact_label_es(f.fact_group, f.fact_key),
            rh_lead_fact_value_es(f.fact_group, f.fact_key, f.fact_value)
        ) AS active_facts_es,
        string_agg(
            '• ' || rh_lead_fact_label_es(f.fact_group, f.fact_key) || ': ' || rh_lead_fact_value_es(f.fact_group, f.fact_key, f.fact_value),
            E'\n'
            ORDER BY f.updated_at DESC
        ) AS active_facts_text
    FROM rh_lead_facts_v2 f
    WHERE f.is_active = true
    GROUP BY f.lead_key
)
SELECT
    l.lead_key,
    l.display_name,
    l.phone,
    l.source_channel,
    l.lead_status,
    l.effective_funnel_stage AS funnel_stage,
    c.stage_label AS funnel_stage_label,
    c.stage_order AS funnel_stage_order,
    l.effective_next_best_action AS next_best_action,
    l.effective_memory_summary AS memory_summary,
    l.facts_summary,
    l.risk_level,
    l.requires_human,
    l.first_seen_at,
    l.last_seen_at,
    l.updated_at,
    fa.active_facts,
    fa.active_facts_es,
    fa.active_facts_text,
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
FROM lead_effective l
LEFT JOIN rh_funnel_stage_catalog_v2 c
    ON c.stage_key = l.effective_funnel_stage
LEFT JOIN facts_agg fa
    ON fa.lead_key = l.lead_key;

COMMIT;
