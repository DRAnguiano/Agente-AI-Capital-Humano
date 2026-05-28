-- =========================================================
-- 004_lead_memory_priority_guards.sql
-- Guardas de prioridad para el estado analítico del lead.
--
-- Importante:
-- - Esto NO gobierna la conversación del bot.
-- - Solo corrige la etapa visible para RH / Power BI cuando ya existe
--   un hecho operativo más importante que la última intención.
--
-- Ejemplo:
-- Si el candidato dijo "mi apto vence en 2 meses" y después pregunta por pago,
-- la conversación puede responder pago, pero el embudo debe conservar:
-- apto_pending_update.
-- =========================================================

BEGIN;

CREATE OR REPLACE FUNCTION rh_leads_v2_apply_priority_guards()
RETURNS trigger AS $$
BEGIN
    -- Apto vencido/próximo a vencer tiene prioridad operativa para RH.
    -- No debe ser rebajado por mensajes posteriores de perfil, pago o smalltalk.
    IF (NEW.facts_summary ? 'document.apto_status')
       AND COALESCE(NEW.facts_summary->>'document.apto_status', '') IN ('expires_in_2_months', 'pending_update', 'expired')
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

-- Corrige leads existentes que ya tengan el hecho de apto guardado.
UPDATE rh_leads_v2
SET
    funnel_stage = 'apto_pending_update',
    next_best_action = 'Dar seguimiento cuando el candidato actualice apto médico.',
    memory_summary = 'El candidato mencionó que su apto médico está vencido o próximo a vencer.',
    updated_at = now()
WHERE facts_summary ? 'document.apto_status'
  AND COALESCE(facts_summary->>'document.apto_status', '') IN ('expires_in_2_months', 'pending_update', 'expired')
  AND COALESCE(funnel_stage, 'new') NOT IN ('human_review', 'lost', 'closed');

COMMIT;
