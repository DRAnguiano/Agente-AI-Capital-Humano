> Convención: RED-first (test que falla → implementación → GREEN). Tests Groq-free,
> corren en `api-test`. Verificación end-to-end por webhook real a Chatwoot (como `local_laguna`).

## 1. Extracción determinista de facts (current_turn)

- [ ] 1.1 RED: tests de `experience.non_target_vehicle_type` (torton/rabón/reparto local/interurbano → fact normalizado; sin evidencia → no escribe; no sobrescribe full/sencillo confirmado)
- [ ] 1.2 Implementar detección por catálogo/keywords en `app/knowledge/current_turn.py` → `experience.non_target_vehicle_type`
- [ ] 1.3 RED+impl: señal de ausencia de experiencia en carretera (`experience.road_experience="none"`): "no he manejado tracto", "quiero aprender" → sí; años/unidad declarada → no
- [ ] 1.4 RED+impl: fact de intención B1/EUA (`experience.b1_us_intent`): B1/EUA/USA/cruce → sí; mención como duda → no (negativo)
- [ ] 1.5 RED+impl: fact de reingreso (`candidate.reingreso`): "ya trabajé en Transmontes y quiero regresar" → sí
- [ ] 1.6 RED+impl: unidad ambigua (tráiler/quinta rueda/caja seca/camión sin precisar) → NO confirma `experience.vehicle_type` + persiste `experience.vehicle_type_pending`; "full"/"sencillo" explícito → confirma y no marca pending
- [ ] 1.7 Verificar persistencia aditiva de los nuevos `fact_key` en `rh_lead_facts_v2` (sin DDL destructivo) y que cargan en el dict `facts` del turno

## 2. Emisión de labels (calculate_candidate_labels)

- [ ] 2.1 RED: matriz de la tricotomía experiencia-objetivo (objetivo_full_sencillo / considerar_escuelita_transmontes / cecati_sugerido) con exclusividad mutua y precedencia objetivo > escuelita > cecati
- [ ] 2.2 Implementar la resolución con precedencia en `app/chatwoot_note_sync.py` · `calculate_candidate_labels`
- [ ] 2.3 RED+impl: `aclaracion_pendiente` cuando `experience.vehicle_type_pending` y unidad no confirmada; se retira al confirmar full/sencillo
- [ ] 2.4 RED+impl: `considerar_operador_b1` desde `experience.b1_us_intent` → canaliza a humano (marca `requiere_agente`/revisión), no bloquea el resto del perfil
- [ ] 2.5 RED+impl: `reingreso_verificar` desde `candidate.reingreso` → terminal: remueve `bot_activo` + `requires_human`
- [ ] 2.6 RED+impl: `falta_ciudad` sin `candidate.city`; `falta_experiencia` sin ninguna señal de experiencia (unidad/años/no-objetivo/ausencia); se retiran al completarse
- [ ] 2.7 Tests de interacción con `perfil_listo` (objetivo+listo OK; no-objetivo / aclaración / reingreso NO permiten `perfil_listo`)
- [ ] 2.8 Verificar que solo se emiten labels del catálogo oficial (sin deprecadas `cecati`/`escuelita`) — extender el guard existente si hace falta

## 3. Wiring del contexto del worker

- [ ] 3.1 Confirmar/ajustar que `app/tasks_chatwoot.py` pasa los nuevos facts a `calculate_candidate_labels` (sin cambio de firma)
- [ ] 3.2 Corregir DEUDA copy `app/persona_config.py` "más de 6 meses de vigencia" → ">3 meses" (alinear con regla vigente)

## 4. Verificación y cierre

- [ ] 4.1 Suite completa Groq-free en `api-test` verde (sin regresión en `test_candidate_labels`/`test_call_scheduling`)
- [ ] 4.2 Rebuild `hr-rag-api` + recreate `api`/`worker`; pruebas end-to-end por webhook: caso objetivo, caso no-objetivo (escuelita), caso B1, caso reingreso, caso unidad ambigua → verificar labels emitidas
- [ ] 4.3 `openspec validate live-label-completion --strict` + `openspec validate --specs --strict`
- [ ] 4.4 Sincronizar deltas a specs principales y archivar el change
- [ ] 4.5 Cerrar el drift de bookkeeping: marcar como superadas las tasks vigentes consolidadas (multi-intent 10a.1–10a.8, business-route C7.4, chatwoot-ai-note objetivo_full_sencillo)
