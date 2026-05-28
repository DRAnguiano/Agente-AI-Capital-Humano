-- =========================================================
-- 005_lead_memory_priority_view_fix.sql
-- Refuerzo de prioridad usando rh_lead_facts_v2 como fuente real.
--
-- Motivo:
-- 004 revisaba facts_summary en rh_leads_v2, pero la fuente más confiable
-- del hecho activo es rh_lead_facts_v2. active_facts de la vista ya mostraba
-- document.apto_status, por lo tanto la prioridad debe leerse desde ahí.
--
-- Esto NO gobierna la conversación; solo corrige el estado analítico visible
-- para RH / Power BI.
-- =========================================================

BEGIN;

-- ---------------------------------------------------------
-- 1) Función auxiliar: ¿el lead tiene apto vencido/próximo a actualizar?
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION rh_lead_v2_has_apto_pending(p_lead_key TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM rh_lead_facts_v2 f
        WHERE f.lead_key = p_lead_key
          AND f.is_active = true
          AND f.fact_group = 'document'
          AND f.fact_key = 'apto_status'
          AND f.fact_value IN ('expires_in_2_months', 'pending_update', 'expired')
    );
END;
$$ LANGUAGE plpgsql STABLE;

-- ---------------------------------------------------------
-- 2) Trigger de prioridad leyendo tabla de facts activos.
-- OJO: en BEFORE INSERT puede que los facts aún no existan; por eso también
-- hacemos UPDATE correctivo y la vista calcula etapa efectiva.
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION rh_leads_v2_apply_priority_guards()
RETURNS trigger AS $$
BEGIN
    IF rh_lead_v2_has_apto_pending(NEW.lead_key)
       AND COALESCE(NEW.funnel_stage, 'new') NOT IN ('human_review', 'lost', 'closed') THEN
        NEW.funnel_stage := 'apto_pending_update';

        IF NEW.next_best_action IS NULL
           OR NEW.next_best_action = ''
           OR NEW.next_best_action IN (
                'Resolver dudas de pago/ruta y luego avanzar suavemente a documentos.',
                'Invitar al candidato a enviar documentos cuando tenga oportunidad, sin presionarlo.'
           ) THEN
            NEW.next_best_action := 'Dar seguimiento cuando el candidato actualice apto médico.';
        END IF;

        IF NEW.memory_summary IS NULL
           OR NEW.memory_summary = ''
           OR NEW.memory_summary IN (
                'El candidato preguntó por pago/compensación.',
                'El candidato preguntó por documentos o requisitos.'
           ) THEN
            NEW.memory_summary := 'El candidato mencionó que su apto médico está vencido o próximo a vencer.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_rh_leads_v2_priority_guards ON rh_leads_v2;

CREATE TRIGGER trg_rh_leads_v2_priority_guards
BEFORE INSERT OR UPDATE ON rh_leads_v2
FOR EACH ROW
EXECUTE FUNCTION rh_leads_v2_apply_priority_guards();

-- ---------------------------------------------------------
-- 3) Corrección de leads existentes usando facts activos.
-- ---------------------------------------------------------
UPDATE rh_leads_v2 l
SET
    funnel_stage = 'apto_pending_update',
    next_best_action = 'Dar seguimiento cuando el candidato actualice apto médico.',
    memory_summary = 'El candidato mencionó que su apto médico está vencido o próximo a vencer.',
    facts_summary = COALESCE(l.facts_summary, '{}'::jsonb) || jsonb_build_object('document.apto_status', f.fact_value),
    updated_at = now()
FROM rh_lead_facts_v2 f
WHERE f.lead_key = l.lead_key
  AND f.is_active = true
  AND f.fact_group = 'document'
  AND f.fact_key = 'apto_status'
  AND f.fact_value IN ('expires_in_2_months', 'pending_update', 'expired')
  AND COALESCE(l.funnel_stage, 'new') NOT IN ('human_review', 'lost', 'closed');

-- ---------------------------------------------------------
-- 4) Vista reforzada: aunque el campo físico se rezague, la vista presenta
-- el estado efectivo correcto para RH/Power BI.
-- ---------------------------------------------------------
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
FROM lead_effective l
LEFT JOIN rh_funnel_stage_catalog_v2 c
    ON c.stage_key = l.effective_funnel_stage;

COMMIT;
