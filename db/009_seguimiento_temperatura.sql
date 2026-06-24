-- =============================================================================
-- Migración 009: Sistema de seguimiento y temperatura de candidatos
-- =============================================================================

-- Tabla de tareas de seguimiento automático
CREATE TABLE IF NOT EXISTS rh_seguimiento_tareas (
    id              bigserial PRIMARY KEY,
    lead_key        text NOT NULL REFERENCES rh_leads_v2(lead_key) ON DELETE CASCADE,

    -- Tipo: 'mensaje_seguimiento' | 'solicitud_llamada' | 'nota_interna'
    tipo            text NOT NULL DEFAULT 'mensaje_seguimiento',

    -- Estado: 'pendiente' | 'enviado' | 'omitido' | 'cancelado'
    estado          text NOT NULL DEFAULT 'pendiente',

    intento         int  NOT NULL DEFAULT 1,
    max_intentos    int  NOT NULL DEFAULT 3,
    clave_plantilla text NOT NULL,
    variables       jsonb NOT NULL DEFAULT '{}',
    programado_para timestamptz NOT NULL,
    enviado_en      timestamptz,
    motivo_omision  text,

    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT rh_seguimiento_estado_check
        CHECK (estado IN ('pendiente', 'enviado', 'omitido', 'cancelado')),
    CONSTRAINT rh_seguimiento_tipo_check
        CHECK (tipo IN ('mensaje_seguimiento', 'solicitud_llamada', 'nota_interna'))
);

-- Índice para el sender: tareas pendientes ordenadas por tiempo de envío
CREATE INDEX IF NOT EXISTS idx_seguimiento_pendientes
    ON rh_seguimiento_tareas (programado_para ASC)
    WHERE estado = 'pendiente';

-- Índice para el scheduler: evitar duplicados por lead
CREATE INDEX IF NOT EXISTS idx_seguimiento_lead_estado
    ON rh_seguimiento_tareas (lead_key, estado, tipo);

-- Un solo intento activo por lead y tipo a la vez
CREATE UNIQUE INDEX IF NOT EXISTS idx_seguimiento_un_pendiente_por_lead_tipo
    ON rh_seguimiento_tareas (lead_key, tipo)
    WHERE estado = 'pendiente';


-- =============================================================================
-- Vista: temperatura de leads activos
-- Expone temperatura calculada + IDs de Chatwoot para el sender
-- =============================================================================
CREATE OR REPLACE VIEW v_temperatura_leads AS
SELECT
    l.lead_key,
    l.display_name,
    l.phone,
    l.source_channel,
    l.lead_status,
    l.funnel_stage,
    l.risk_level,
    l.requires_human,
    l.last_seen_at,
    l.updated_at,

    -- Horas sin actividad del candidato
    EXTRACT(EPOCH FROM (now() - l.last_seen_at)) / 3600.0  AS horas_inactivo,

    -- Temperatura calculada
    CASE
        WHEN EXTRACT(EPOCH FROM (now() - l.last_seen_at)) / 3600 < 24   THEN 'caliente'
        WHEN EXTRACT(EPOCH FROM (now() - l.last_seen_at)) / 3600 < 72   THEN 'tibio'
        WHEN EXTRACT(EPOCH FROM (now() - l.last_seen_at)) / 3600 < 168  THEN 'enfriando'
        WHEN EXTRACT(EPOCH FROM (now() - l.last_seen_at)) / 3600 < 504  THEN 'frio'
        ELSE 'perdido'
    END AS temperatura,

    -- Seguimientos ya enviados (para respetar max_intentos)
    (
        SELECT COUNT(*)
        FROM rh_seguimiento_tareas t
        WHERE t.lead_key = l.lead_key
          AND t.estado = 'enviado'
          AND t.tipo = 'mensaje_seguimiento'
    ) AS seguimientos_enviados,

    -- Cuándo se envió el último seguimiento (para espaciar intentos)
    (
        SELECT t.enviado_en
        FROM rh_seguimiento_tareas t
        WHERE t.lead_key = l.lead_key
          AND t.estado = 'enviado'
          AND t.tipo = 'mensaje_seguimiento'
        ORDER BY t.enviado_en DESC
        LIMIT 1
    ) AS ultimo_seguimiento_en,

    -- Próximo seguimiento pendiente
    (
        SELECT t.programado_para
        FROM rh_seguimiento_tareas t
        WHERE t.lead_key = l.lead_key
          AND t.estado = 'pendiente'
        ORDER BY t.programado_para ASC
        LIMIT 1
    ) AS proximo_seguimiento,

    -- IDs de Chatwoot para envío directo
    lc.chatwoot_account_id,
    lc.chatwoot_conversation_id

FROM rh_leads_v2 l
LEFT JOIN rh_lead_conversations_v2 lc
    ON lc.lead_key = l.lead_key
   AND lc.chatwoot_conversation_id IS NOT NULL
   AND lc.chatwoot_account_id IS NOT NULL
WHERE l.lead_status IN ('open', 'followup_pending', 'human_review');
