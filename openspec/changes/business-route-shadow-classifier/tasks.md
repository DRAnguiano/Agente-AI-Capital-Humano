# Tasks — business-route-shadow-classifier

> Shadow-only. Sin activación productiva hasta ≥ 80% PASS_STRONG en harness QA (224 casos).
> Sin commits ni push hasta aprobación explícita de David.

## C1. Schema / contrato de output (P0)
- [x] C1.1 Crear `app/knowledge/business_route_schema.py`: dataclasses `RequestedInfoItem`,
      `ExplicitFact`, `BusinessSignal`, `AmbiguityFlag`, `BusinessRouteOutput` — sin lógica,
      solo tipos. Incluye catálogos `BUSINESS_SIGNALS`, `VALID_VEHICLE_TYPES`,
      `HUMAN_REQUIRED_SIGNALS`, helpers `has_signal()`, `signal_names()`, `flag_names()`,
      `to_dict()`, `safe_empty()`.
- [x] C1.2 Validado: el schema no importa DB, Chatwoot ni LLM (solo stdlib/typing/dataclasses).
- [x] C1.3 Test `tests/test_business_route_schema.py`: instanciación de todos los dataclasses,
      to_dict, safe_empty, has_signal, signal_names, flag_names, VALID_VEHICLE_TYPES catalog.

## C2. Extracción de vehicle_type + señales de negocio (P0)

> Implementación: pipeline LLM-propone / policy-valida en lugar de detector determinista
> separado. El LLM propone explicit_facts y business_signals; el policy validator
> (`validate_business_output`) los verifica contra el catálogo de dominio sin regex ad-hoc.

- [x] C2.1 LLM propone `experience.vehicle_type` en `explicit_facts`. Policy valida usando
      `normalize_domain_values.normalize_vehicle` sobre el campo `evidence`. Sin regex ad-hoc.
- [x] C2.2–C2.6 Cubiertos por `test_business_route_policy.py` y `test_business_route_classifier.py`:
      sencillo/full kept; quinta rueda/trailer rejected → jerga flag; torton → escuelita;
      trailero → ambiguity (substring match NEEDS_CLARIFICATION).

## C3. Detección de business_signals (P0)

> Implementación: LLM clasifica señales; policy valida contra `BUSINESS_SIGNALS` catalog
> y umbrales de confidence. Auto-corrección cuando vehicle_type fact es rechazado.

- [x] C3.1–C3.9 Cubiertos por policy y classifier tests: objetivo_full_sencillo,
      jerga_ambigua, escuelita, cecati, B1+requires_human, reingreso+requires_human,
      negativos (torton ≠ objetivo_full_sencillo, quinta rueda ≠ vehicle_type confirmado).

## C4. Policy validator — guard de evidencia (P1)
- [x] C4.1 `validate_business_output(output, text, canonical_profile) → BusinessRouteOutput`
      en `app/knowledge/business_route_policy.py`: elimina facts sin evidencia literal o con
      confidence < 0.7; elimina señales desconocidas o con confidence < 0.4; fuerza
      requires_human para HUMAN_REQUIRED_SIGNALS; detecta conflicto de ciudad vs perfil.
- [x] C4.2 Test: fact con `evidence=""` → eliminado.
- [x] C4.3 Test: señal con `confidence=0.3` → eliminada.
- [x] C4.4 Test: output válido con sencillo/full pass.

## C5. Integración shadow — clasificador completo (P1)
- [x] C5.1 `classify_business_route_shadow(text, *, canonical_profile, asked_field_keys,
      missing_fields, conversational_classification) → BusinessRouteOutput` en
      `app/knowledge/business_route_classifier.py`. Orquesta LLM + policy. Sin escritura DB.
- [x] C5.2 Verificado: `business_route_classifier.py` no importa `app.db`,
      `tasks_chatwoot` ni `app.app`.
- [x] C5.3 Test smoke (mock): "Me interesa para sencillo" → `objetivo_full_sencillo`.
- [x] C5.4 Test smoke (mock): "5ta rueda" → `vehicle_type_ambiguous` flag,
      `jerga_ambigua_falta_unidad` signal.

## C6. Harness QA — integración shadow output (P1)

> Implementación real: flag `--include-business-shadow` (no `--mode shadow`): el shadow
> corre además del modo base elegido y agrega columnas `business_*` al reporte.
> Read-only. Errores por fila (`business_shadow_status=ERROR` + `business_shadow_error`)
> sin abortar la corrida. El presupuesto diario usa tokens efectivos (base + shadow).

- [x] C6.1 Flag `--include-business-shadow` en `scripts/qa_response_matrix.py`:
      `_make_row_fn` envuelve el row-fn base y `_run_business_shadow` llama
      `classify_business_route_shadow()` por caso. Nunca lanza.
      Tests: `tests/test_qa_response_matrix.py` (mocks, sin LLM).
- [x] C6.2 Columnas nuevas `business_*` en el reporte (`SHADOW_COLUMNS`): JSON completo
      (`business_requested_info`, `business_explicit_facts`, `business_signals`,
      `business_ambiguity_flags`, `business_policy_answer_keys`,
      `business_validation_errors`) + escalares (`business_requires_human`,
      `business_profile_action`, `business_signal_names`,
      `business_requested_info_topics`, `business_fact_keys`,
      `business_ambiguity_names`, `business_shadow_status`, `business_shadow_error`,
      `profile_context_available`). Sin solapamiento con `OUTPUT_COLUMNS` (test).
- [ ] C6.3 Correr `--include-business-shadow --priority Alta` y registrar baseline.
- [ ] C6.4 Correr los 224 casos completos con shadow → baseline para activación.
      Pendientes asociados: qa_0219 reintento (RateLimit); qa_0220–qa_0224 holdout ciego;
      qa_0216–qa_0218 ya cubiertos como regresiones en tests.

## C7. Criterio de activación productiva (P2, bloqueado por C5/C6)
- [ ] C7.1 ≥ 80% de los 224 casos con `shadow_business_signals` correctos vs `route_esperada_sugerida`.
- [ ] C7.2 0 casos con fact inventado (evidence vacío en output final).
- [ ] C7.3 Revisión humana de todos los REVIEW_MAPPING y CONTRACT_GAP antes de activar.
- [ ] C7.4 Change separado para wiring productivo (no en este change).
