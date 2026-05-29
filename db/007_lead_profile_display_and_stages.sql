-- =========================================================
-- 007_lead_profile_display_and_stages.sql
-- Etiquetas en español para facts nuevos de perfilamiento
-- y etapas nuevas del embudo RH.
--
-- Mantiene llaves técnicas internas, pero RH/Power BI ven texto humano.
-- =========================================================

BEGIN;

-- ---------------------------------------------------------
-- 1) Etapas nuevas del embudo
-- ---------------------------------------------------------
INSERT INTO rh_funnel_stage_catalog_v2 (stage_key, stage_label, stage_order, description, is_terminal)
VALUES
    ('profile_in_progress', 'Perfilamiento en progreso', 45, 'El candidato compartió algunos datos útiles, pero falta completar perfil mínimo.', false),
    ('profiled_viable', 'Perfil viable inicial', 65, 'El candidato parece viable por información declarada; falta confirmar interés y documentación.', false),
    ('potential_candidate_documents_pending', 'Candidato potencial / documentación por enviar', 75, 'El candidato indica contar con documentación y queda pendiente de enviarla.', false),
    ('potential_candidate_documents_sent', 'Candidato potencial / documentos por validar', 85, 'El candidato indica que ya envió documentación; Capital Humano debe validarla.', false),
    ('blocked_document_update', 'Perfil con documento por actualizar', 72, 'El candidato tiene licencia, apto u otro documento vencido o próximo a vencer.', false)
ON CONFLICT (stage_key) DO UPDATE SET
    stage_label = EXCLUDED.stage_label,
    stage_order = EXCLUDED.stage_order,
    description = EXCLUDED.description,
    is_terminal = EXCLUDED.is_terminal;

-- ---------------------------------------------------------
-- 2) Etiquetas amigables para nuevos facts
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION rh_lead_fact_label_es(p_fact_group TEXT, p_fact_key TEXT)
RETURNS TEXT AS $$
DECLARE
    k TEXT := COALESCE(p_fact_group, '') || '.' || COALESCE(p_fact_key, '');
BEGIN
    RETURN CASE k
        WHEN 'role_fit.operator_type' THEN 'Tipo de operador'
        WHEN 'document.apto_status' THEN 'Apto médico'
        WHEN 'documents.submission_status' THEN 'Documentos'
        WHEN 'documents.availability_claim' THEN 'Disponibilidad de documentos'
        WHEN 'documents.labor_letters_status' THEN 'Cartas laborales'
        WHEN 'interest.payment' THEN 'Interés en pago'
        WHEN 'interest.requirements_documents' THEN 'Interés en requisitos'
        WHEN 'interest.routes' THEN 'Interés en rutas'
        WHEN 'candidate.city' THEN 'Ciudad'
        WHEN 'candidate.age' THEN 'Edad'
        WHEN 'candidate.availability_status' THEN 'Disponibilidad del candidato'
        WHEN 'candidate.vacancy_accepted' THEN 'Aceptación de vacante'
        WHEN 'license.category' THEN 'Tipo de licencia'
        WHEN 'license.status' THEN 'Estado de licencia'
        WHEN 'license.expires_in' THEN 'Vigencia de licencia'
        WHEN 'license.expires_at' THEN 'Vencimiento de licencia'
        WHEN 'medical.apto_status' THEN 'Apto médico'
        WHEN 'medical.apto_expires_in' THEN 'Vigencia de apto médico'
        WHEN 'medical.apto_expires_at' THEN 'Vencimiento de apto médico'
        WHEN 'experience.years' THEN 'Años de experiencia'
        WHEN 'experience.fifth_wheel' THEN 'Experiencia quinta rueda/full'
        WHEN 'experience.carretera_mexicana' THEN 'Experiencia en carretera mexicana'
        WHEN 'dropoff.last_bot_topic_before_silence' THEN 'Último tema antes de silencio'
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
        WHEN k = 'documents.submission_status' AND v = 'pending_candidate_will_send'
            THEN 'Pendiente; el candidato los enviará después'
        WHEN k = 'documents.availability_claim' AND v = 'candidate_says_available'
            THEN 'El candidato indica que cuenta con ellos'
        WHEN k = 'documents.labor_letters_status' AND v = 'available'
            THEN 'Cuenta con cartas laborales'
        WHEN k = 'interest.payment' AND v = 'asked'
            THEN 'Preguntó por pago'
        WHEN k = 'interest.requirements_documents' AND v = 'asked'
            THEN 'Preguntó por requisitos/documentos'
        WHEN k = 'interest.routes' AND v = 'asked'
            THEN 'Preguntó por rutas'
        WHEN k = 'candidate.availability_status' AND v = 'en_ruta_o_no_disponible_ahora'
            THEN 'Viene manejando o no puede enviar documentos ahora'
        WHEN k = 'candidate.vacancy_accepted' AND v = 'sí'
            THEN 'Le interesa continuar'
        WHEN k = 'license.status' AND v = 'vigente'
            THEN 'Vigente'
        WHEN k = 'license.status' AND v = 'vencida'
            THEN 'Vencida'
        WHEN k = 'medical.apto_status' AND v = 'vigente'
            THEN 'Vigente'
        WHEN k = 'medical.apto_status' AND v = 'vencido'
            THEN 'Vencido'
        WHEN k = 'experience.fifth_wheel' AND v = 'sí'
            THEN 'Sí'
        WHEN k = 'experience.carretera_mexicana' AND v = 'sí'
            THEN 'Sí'
        ELSE initcap(replace(v, '_', ' '))
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ---------------------------------------------------------
-- 3) Función de etapa efectiva desde facts activos
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION rh_lead_v2_effective_stage(p_lead_key TEXT, p_current_stage TEXT)
RETURNS TEXT AS $$
DECLARE
    has_apto_pending BOOLEAN;
    has_docs_pending_send BOOLEAN;
    has_city BOOLEAN;
    has_license_category BOOLEAN;
    has_license_status BOOLEAN;
    has_apto_status BOOLEAN;
    has_experience BOOLEAN;
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

    SELECT EXISTS (
        SELECT 1 FROM rh_lead_facts_v2 f
        WHERE f.lead_key = p_lead_key AND f.is_active = true
          AND f.fact_group = 'documents'
          AND f.fact_key = 'submission_status'
          AND f.fact_value = 'pending_candidate_will_send'
    ) INTO has_docs_pending_send;

    IF has_docs_pending_send THEN
        RETURN 'potential_candidate_documents_pending';
    END IF;

    SELECT
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'candidate' AND f.fact_key = 'city'),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'license' AND f.fact_key = 'category'),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'license' AND f.fact_key IN ('status', 'expires_in', 'expires_at')),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'medical' AND f.fact_key IN ('apto_status', 'apto_expires_in', 'apto_expires_at')),
        EXISTS (SELECT 1 FROM rh_lead_facts_v2 f WHERE f.lead_key = p_lead_key AND f.is_active = true AND f.fact_group = 'experience' AND f.fact_key IN ('fifth_wheel', 'years'))
    INTO has_city, has_license_category, has_license_status, has_apto_status, has_experience;

    IF has_city AND has_license_category AND has_apto_status AND has_experience THEN
        RETURN 'profiled_viable';
    END IF;

    IF has_city OR has_license_category OR has_license_status OR has_apto_status OR has_experience THEN
        RETURN 'profile_in_progress';
    END IF;

    RETURN COALESCE(p_current_stage, 'new');
END;
$$ LANGUAGE plpgsql STABLE;

-- ---------------------------------------------------------
-- 4) Vista reforzada con etapa efectiva y texto RH
-- ---------------------------------------------------------
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
                THEN 'El candidato indica que puede compartir documentación después; queda pendiente de envío.'
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
