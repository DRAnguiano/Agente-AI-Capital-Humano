# Tasks — business-route-shadow-classifier

> Shadow-only. Sin activación productiva hasta ≥ 80% PASS_STRONG en harness QA (224 casos).
> Sin commits ni push hasta aprobación explícita de David.

## C1. Schema / contrato de output (P0)
- [ ] C1.1 Crear `app/knowledge/business_route_schema.py`: dataclasses `ExplicitFact`,
      `BusinessSignal`, `AmbiguityFlag`, `BusinessRouteOutput` — sin lógica, solo tipos.
- [ ] C1.2 Validar que el schema no importa ni DB, ni Chatwoot, ni LLM (solo stdlib/typing).
- [ ] C1.3 Test `tests/test_business_route_schema.py`: instanciar cada dataclass con valores
      válidos e inválidos; verificar que confidence fuera de [0,1] falla.

## C2. Extracción de vehicle_type (reutiliza catálogo) (P0)
- [ ] C2.1 `extract_vehicle_fact(text) → tuple[ExplicitFact | None, AmbiguityFlag | None]`:
      reutiliza `normalize_domain_values.normalize_vehicle` + `applies_objetivo_full_sencillo`.
      Sin regex ad-hoc.
- [ ] C2.2 Test: "Me interesa para sencillo" → `ExplicitFact(value="sencillo", confidence ≥ 0.95)`.
- [ ] C2.3 Test: "manejo tracto full" → `ExplicitFact(value="full")`.
- [ ] C2.4 Test: "quinta rueda" → `AmbiguityFlag(name="vehicle_type_ambiguous")`, no fact.
- [ ] C2.5 Test: "torton" → no fact, no ambiguity flag (non-target, señal escuelita en C3).
- [ ] C2.6 Test: "trailero" → ambiguity flag (substring match a `trailer` NEEDS_CLARIFICATION).

## C3. Detección de business_signals (P0)
- [ ] C3.1 `detect_business_signals(text, intent, facts) → list[BusinessSignal]`:
      lógica determinista basada en catálogo y hechos ya extraídos.
- [ ] C3.2 Test `objetivo_full_sencillo`: full/sencillo confirmado → señal emitida.
- [ ] C3.3 Test `jerga_ambigua_falta_unidad`: quinta rueda/tráiler/trailero → señal emitida.
- [ ] C3.4 Test `considerar_escuelita_transmontes`: torton/rabón/reparto → señal emitida.
- [ ] C3.5 Test `cecati_sugerido`: "no tengo experiencia", "quiero aprender" → señal emitida.
- [ ] C3.6 Test `considerar_operador_b1`: "busco B1", "vacante Estados Unidos" → señal +
      `requires_human=True`.
- [ ] C3.7 Test `reingreso_verificar`: "ya trabajé ahí", "quiero volver" → señal +
      `requires_human=True`.
- [ ] C3.8 Test negativo: "torton" NO produce `objetivo_full_sencillo`.
- [ ] C3.9 Test negativo: "quinta rueda" NO produce `vehicle_type=full` ni `vehicle_type=sencillo`.

## C4. Policy router — guard de evidencia (P1)
- [ ] C4.1 `policy_router_validate(output: BusinessRouteOutput) → BusinessRouteOutput`:
      elimina facts sin evidencia literal; elimina señales con confidence < 0.7.
- [ ] C4.2 Test: fact con `evidence=""` → eliminado del output.
- [ ] C4.3 Test: señal con `confidence=0.5` → eliminada.
- [ ] C4.4 Test: output válido pasa sin modificaciones.

## C5. Integración shadow — clasificador completo (P1)
- [ ] C5.1 `classify_business_route(text: str) → BusinessRouteOutput`:
      orquesta `classify_message()` + `extract_explicit_facts()` + `detect_business_signals()`
      + `policy_router_validate()`. Sin escritura a DB.
- [ ] C5.2 Verificar que `classify_business_route` no importa `db.py`, `tasks_chatwoot.py`
      ni ningún módulo que escriba estado.
- [ ] C5.3 Test smoke: "Me interesa para sencillo" → output completo con señal `objetivo_full_sencillo`.
- [ ] C5.4 Test smoke: "5ta rueda" → ambiguity_flag `vehicle_type_ambiguous`, señal
      `jerga_ambigua_falta_unidad`.

## C6. Harness QA — integración shadow output (P1)
- [ ] C6.1 Añadir `--mode shadow` a `scripts/qa_response_matrix.py`: llama
      `classify_business_route()` en lugar de solo `classify_message()`.
- [ ] C6.2 Columnas nuevas en reporte: `shadow_business_signals`, `shadow_explicit_facts`,
      `shadow_ambiguity_flags`, `shadow_requires_human`.
- [ ] C6.3 Correr `--mode shadow --priority Alta` (13 casos) y registrar baseline.
- [ ] C6.4 Correr `--mode shadow` 224 casos completos → baseline para activación.

## C7. Criterio de activación productiva (P2, bloqueado por C5/C6)
- [ ] C7.1 ≥ 80% de los 224 casos con `shadow_business_signals` correctos vs `route_esperada_sugerida`.
- [ ] C7.2 0 casos con fact inventado (evidence vacío en output final).
- [ ] C7.3 Revisión humana de todos los REVIEW_MAPPING y CONTRACT_GAP antes de activar.
- [ ] C7.4 Change separado para wiring productivo (no en este change).
