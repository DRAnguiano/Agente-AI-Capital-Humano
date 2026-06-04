-- =============================================================================
-- 010_v_rh_lead_facts_canonical.sql  —  Fase 2A
-- Vista de COMPATIBILIDAD de LECTURA (read-only). NO destructiva.
--   * NO modifica rh_lead_facts_v2 (sin ALTER/UPDATE/DELETE).
--   * NO toca v_rh_work_queue ni el flujo vivo.
--   * Reversible con DROP VIEW (ver final del archivo).
-- Expone cada fact con clave/valor/estado CANÓNICO + columnas raw (trazabilidad),
-- para que futuros lectores/planners (Fase 2B: canonical_profile_reader /
-- funnel_state_planner) lean facts canónicos sin romper a los consumidores legacy.
-- La vista NO decide preguntas; solo normaliza la lectura.
-- =============================================================================

CREATE OR REPLACE VIEW v_rh_lead_facts_canonical AS
SELECT
    f.lead_key,
    f.is_active,
    f.confidence,
    f.source,
    f.observed_at,

    -- ── trazabilidad (nunca se pierde el original) ──
    f.fact_group AS raw_group,
    f.fact_key   AS raw_key,
    f.fact_value AS raw_value,

    -- ── canonical_group ──
    CASE
        WHEN f.fact_group = 'license'   AND f.fact_key = 'category'           THEN 'license'   -- A
        WHEN f.fact_group = 'document'  AND f.fact_key = 'apto_status'        THEN 'medical'   -- B
        WHEN f.fact_group = 'documents' AND f.fact_key = 'availability_claim' THEN 'candidate' -- E
        ELSE f.fact_group                                                                      -- C,D,F,G,H,I
    END AS canonical_group,

    -- ── canonical_key ──
    CASE
        WHEN f.fact_group = 'license'   AND f.fact_key = 'category'           THEN 'type'                            -- A
        WHEN f.fact_group = 'documents' AND f.fact_key IN ('labor_letters','labor_letters_status') THEN 'proof'     -- C
        WHEN f.fact_group = 'documents' AND f.fact_key = 'availability_claim' THEN 'availability_to_attend_candidate' -- E
        ELSE f.fact_key                                                                                            -- B,D,F,G,H,I
    END AS canonical_key,

    -- ── canonical_value ──
    CASE
        -- C) documents.proof: solo valores claros; si no, se conserva raw_value
        WHEN f.fact_group = 'documents' AND f.fact_key IN ('labor_letters','labor_letters_status') THEN
            CASE
                WHEN lower(f.fact_value) IN ('sí','si','yes','true','available','disponible') THEN 'cartas'
                WHEN lower(f.fact_value) IN ('semanas_imss','semanas imss','imss')            THEN 'semanas_imss'
                WHEN lower(f.fact_value) IN ('no','ninguno','sin documentos')                 THEN 'ninguno'
                ELSE f.fact_value
            END
        -- G) experience.years: solo dígitos (string "10 años" -> "10")
        WHEN f.fact_group = 'experience' AND f.fact_key = 'years' THEN
            NULLIF(regexp_replace(f.fact_value, '[^0-9]', '', 'g'), '')
        -- H) vehicle_type=quinta_rueda: NO se expone como valor final
        WHEN f.fact_group = 'experience' AND f.fact_key = 'vehicle_type' AND f.fact_value = 'quinta_rueda' THEN NULL
        -- A,B,D,E,F,I) sin transformación de valor
        ELSE f.fact_value
    END AS canonical_value,

    -- ── canonical_unit ──
    CASE
        WHEN f.fact_group = 'experience' AND f.fact_key = 'years' THEN 'years'  -- G
        ELSE NULL
    END AS canonical_unit,

    -- ── canonical_state ──
    CASE
        -- H) vehicle_type legacy quinta_rueda
        WHEN f.fact_group = 'experience' AND f.fact_key = 'vehicle_type' AND f.fact_value = 'quinta_rueda'
            THEN 'legacy_needs_clarification'
        -- A) license.type fuera de catálogo (B/E/A/C)
        WHEN f.fact_group = 'license' AND f.fact_key = 'category' AND upper(f.fact_value) NOT IN ('B','E','A','C')
            THEN 'needs_review'
        -- B) apto mapeado desde grupo 'document' (conflicto NO se resuelve aquí)
        WHEN f.fact_group = 'document' AND f.fact_key = 'apto_status'
            THEN 'mapped_from_document_group'
        -- C) documents.proof: claro -> mapped_to_proof; si no -> needs_review
        WHEN f.fact_group = 'documents' AND f.fact_key IN ('labor_letters','labor_letters_status') THEN
            CASE
                WHEN lower(f.fact_value) IN ('sí','si','yes','true','available','disponible',
                                             'semanas_imss','semanas imss','imss',
                                             'no','ninguno','sin documentos')
                    THEN 'mapped_to_proof'
                ELSE 'needs_review'
            END
        -- D) submission_status: estado de entrega, NO es proof
        WHEN f.fact_group = 'documents' AND f.fact_key = 'submission_status'
            THEN 'separate_delivery_state'
        -- E) availability_claim: candidato a availability_to_attend, NO confirmado
        WHEN f.fact_group = 'documents' AND f.fact_key = 'availability_claim'
            THEN 'review_availability_candidate'
        -- F) general_status: ambiguo
        WHEN f.fact_group = 'documents' AND f.fact_key = 'general_status'
            THEN 'needs_review'
        -- I) resto
        ELSE 'ok'
    END AS canonical_state
FROM rh_lead_facts_v2 f;

-- =============================================================================
-- VALIDACIÓN (read-only; ejecutar manualmente tras crear la vista)
-- =============================================================================
-- Paridad 1:1 (base == vista):
-- SELECT (SELECT count(*) FROM rh_lead_facts_v2) AS base,
--        (SELECT count(*) FROM v_rh_lead_facts_canonical) AS vista;
--
-- Licencias:
-- SELECT canonical_group, canonical_key, canonical_value, canonical_state, count(*)
-- FROM v_rh_lead_facts_canonical
-- WHERE canonical_group='license'
-- GROUP BY 1,2,3,4
-- ORDER BY count(*) DESC;
--
-- Vehicle legacy (quinta_rueda -> canonical_value NULL, state legacy_needs_clarification):
-- SELECT *
-- FROM v_rh_lead_facts_canonical
-- WHERE raw_group='experience' AND raw_key='vehicle_type' AND raw_value='quinta_rueda';
--
-- Documents (revisar mapeos proof / submission / availability / general):
-- SELECT raw_key, raw_value, canonical_key, canonical_value, canonical_state, count(*)
-- FROM v_rh_lead_facts_canonical
-- WHERE raw_group='documents'
-- GROUP BY 1,2,3,4,5
-- ORDER BY raw_key, count(*) DESC;
--
-- Conflicto apto (medical vs document con valores distintos; NO se resuelve en la vista):
-- SELECT m.lead_key, m.fact_value AS medical_apto, d.fact_value AS document_apto
-- FROM rh_lead_facts_v2 m
-- JOIN rh_lead_facts_v2 d
--   ON d.lead_key=m.lead_key AND d.fact_group='document' AND d.fact_key='apto_status'
-- WHERE m.fact_group='medical' AND m.fact_key='apto_status'
--   AND m.fact_value <> d.fact_value;

-- =============================================================================
-- ROLLBACK
-- =============================================================================
-- DROP VIEW IF EXISTS v_rh_lead_facts_canonical;
