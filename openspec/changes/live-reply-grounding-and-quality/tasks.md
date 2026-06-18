# Tasks — live-reply-grounding-and-quality

> Changeset **doc-only**. Estas tasks describen el trabajo de implementación futuro en bloques
> pequeños; quedan sin marcar hasta que cada bloque se implemente con su test verificable.

> [ADOPCIÓN 2026-06-17] Auditoría read-only: B1, B2 y B3 ya estaban implementados y
> testeados por trabajo que aterrizó vía otros changes; este tasks.md (doc-only) no se
> había actualizado. Se marcan [x] con su evidencia. Pendiente real de G6 = B4 + B5.

## B1. Friendly grounding anti-fabricación (P0)
- [x] B1.1 Sin few-shot numérico en el prompt de `_answer_friendly_message`
      (`knowledge_orchestrator.py:564-645`); el comentario no introduce cifras.
- [x] B1.2 Guard anti-fabricación: `_friendly_introduces_number` (orchestrator:559-561,
      aplicado en :631) descarta y usa comentario neutro si el LLM mete números ausentes.
- [x] B1.3 Test `tests/test_friendly_grounding.py`: "ahorita le respondo" → sin dígitos/años.

## B2. Dominio sencillo/full/escuelita (P0)
- [x] B2.1 `sencillo` no se etiqueta "(escuelita)" (label `escuelita` deprecada en nota/labels).
- [x] B2.2 Dominio declarativo en `domain_catalog.py` + `normalize_domain_values.py`:
      `full`/`sencillo` = objetivo confirmable; quinta rueda/tráiler/camión = needs_clarification
      (no fija vehicle_type); `torton`/`rabón`/reparto/local = non_target → escuelita, ≠ full/sencillo.
- [x] B2.3 Test `tests/test_candidate_labels.py`: `test_official_labels_no_escuelita`,
      `test_nota_no_muestra_escuelita_raw`.

## B3. Guard de extracción de edad (P0/P1)
- [x] B3.1 `profile_extractor.py`: no infiere `candidate.age` desde "N años" de experiencia.
- [x] B3.2 Test `tests/test_profile_age_guard.py`: "20 años de fullero" → `experience.years`,
      sin `candidate.age`.

## B4. Higiene de fuentes de conocimiento (P1)
- [ ] B4.1 Auditar `data/00_*`..`data/05_*`: separar instrucción interna de texto respondible.
- [ ] B4.2 Filtro/strip en el prompt de RAG para no devolver instrucciones internas.
- [ ] B4.3 Test: chunk con "Mundo debe..." no aparece en la respuesta final al candidato.

## B5. RAG answer grounding / anti over-retrieval (P1)
- [ ] B5.1 Acotar recuperación/ensamblado a fuentes relacionadas con la pregunta.
- [ ] B5.2 Test: "pago para sencillo" no mezcla paradas autorizadas ni proceso documental.

## B6. Ack dedup en current_turn (P2)
- [x] B6.1 Un solo "Perfecto": `_join_ack_and_question` + `_strip_leading_perfecto`
  (current_turn.py) quitan el doble prefijo; verificado en `test_current_turn_ack.py`.
- [x] B6.2 Sin fact duplicado en el prefijo: el ack toma facts del extractor único
  (`extract_profile_facts_as_dict`, con el guard de edad B3), por lo que no saca
  `candidate.age` desde una frase de experiencia → no hay "20 años, 20 años de experiencia".
- [x] B6.3 Tests: `test_current_turn_ack.py` — ciudad+licencia → un solo "Perfecto" y una
  sola pregunta; "tengo 20 años manejando full" → "20 años de experiencia" una vez, sin dup.

## B7. Cierre de perfil / handoff de llamada (P2)
- [ ] B7.1 Siguiente paso claro al completar perfil o documentos declarados.
- [x] B7.2 Helper compartido `is_business_hours()` — horario **8:00–17:30 L–V**, zona canónica
      `America/Mexico_City`. NO confundir con `followup/ventana.py` (08:30–20:30 L–S, envío async).
      Evidencia: `app/knowledge/business_hours.py` + `current_turn._profile_complete_closing`
      usa el helper; `docker compose --profile test run --rm api-test sh -lc 'PYTHONPATH=/app pytest tests/test_business_hours.py'`
      → 5 passed.
- [x] B7.3 Corregir la rama **en-horario** del cierre: `_profile_complete_closing()`
      ahora indica que queda registrado para que el equipo pueda contactar dentro del
      horario de atencion, sin prometer agenda real. Evidencia:
      `tests/test_current_turn_ack.py::test_profile_complete_closing_in_hours_mentions_team_contact`.
- [ ] B7.4 Estado/label de lead para llamada: `llamada_pendiente` ya existe en el catalogo
      oficial; falta emitirla desde la decision determinista cuando el perfil esta listo
      o requiere agente y el candidato pide/acepta llamada. Registrar ademas
      `scheduling.call_requested=true`, `scheduling.call_status=pending` y
      `scheduling.call_window_text` con el texto del candidato ("manana a las 4", etc.).
      No prometer agenda real: "lo dejo registrado para que el equipo te contacte en horario".
- [ ] B7.5 Validacion de horario solicitado: normalizar/validar contra `is_business_hours`
      (8:00-17:30 L-V, `America/Mexico_City`) cuando el candidato indique una hora clara.
      Guardar `scheduling.call_window_valid=true|false|unknown` y reflejarlo en nota privada
      de Chatwoot como "dentro/fuera/no interpretable del horario de atencion".
- [ ] B7.6 Test: solicitud de llamada en horario/fuera de horario/horario ambiguo ->
      reply visible, label `llamada_pendiente`, facts `scheduling.*` y nota privada correctos.

## B8. Manejo de correcciones explícitas (P0, mayor)
- [x] B8.1 Corrección reformula la respuesta: el valor nuevo se extrae y **sobrescribe** el
      lead/estatus (`upsert_lead_fact` ON CONFLICT DO UPDATE SET fact_value=EXCLUDED) y, al
      confirmar un objetivo claro (full/sencillo), se **limpia la escuelita previa**
      (`_apply_business_rule_overrides`, rama `deterministic_clear_escuelita_on_target`). Sin
      hostigar: el slot corregido queda lleno → `next_question_from_missing_facts` no
      re-pregunta la unidad, avanza. Evidencia: `tests/test_live_corrections.py`.
- [x] B8.2 NO duplica la lógica LLM de corrección de `multi-intent-migration` (6.3/7.2/7.4/
      9.3.3/9.3.11 → `fact_corrections.py`, shadow). El camino vivo reusa `normalize_vehicle`
      (misma resolución de dominio del extractor) y reacciona a que ESTE turno confirme
      full/sencillo, sin detectar el "acto" de corregir por frase. La distinción de dominio ya
      existe: rabón/torton/reparto → `considerar_escuelita_transmontes` (Capital Humano);
      sin experiencia → `cecati_sugerido` (CECATI Gómez Palacio), redactada en `persona_config.py`.
- [x] B8.3 Tests en `tests/test_live_corrections.py`: "en realidad es sencillo"/"manejo full"
      → vehicle_type corregido; objetivo válido NO emite escuelita; turno de experiencia tras
      escuelita no la re-emite; **escuelita previa se limpia** al confirmar objetivo; unidad
      corregida no se re-pregunta. 9 casos verdes + 24 de regresión en `test_live_business_rules.py`.

## B9. Datos sensibles / pagos / trámites con costo (P1)
- [x] B9.1 Guard determinista `_PAID_SENSITIVE_RE` en `knowledge_orchestrator`: ante
      petición de pago/depósito/cuenta-CLABE, el bot responde `_SENSITIVE_PAID_REPLY` que
      aclara que NO maneja pagos/cobros ni pide datos bancarios por ese medio (no solicita
      datos sensibles). El "no solicitar" en generación libre lo refuerza el persona prompt.
- [x] B9.2 Costo al candidato / dato bancario → respuesta controlada "nuestro equipo lo
      confirma por el canal autorizado", sin handoff (el bot aclara y sigue disponible).
      Distingue costo-al-candidato de salario ("cuánto pagan" va por RAG, no dispara).
- [x] B9.3 Tests en `tests/test_live_business_rules.py`: 4 casos de costo/cuenta → reply
      `sensitive_paid_guard` sin pedir datos; 3 de salario → NO disparan el guard.

## B10. Decisión operativa unificada (P1)
- [ ] B10.1 Respuesta visible, nota interna y labels derivan de la misma decisión por turno
      (Postgres/lead_memory): perfil, intención, horario, llamada, humano, bloqueo.
- [ ] B10.2 Test: último mensaje "5" con campo pendiente experiencia → la nota NO dice
      "preguntó por documentos"; acción/bloqueo/labels consistentes con "registró experiencia".

## B11. Labels oficiales / no labels fantasma (P2)
- [x] B11.1 Solo emiten labels del catálogo. `_filter_official_labels` (chatwoot_note_sync)
      ahora mapea aliases fantasma → oficial (`LABEL_ALIASES`) y descarta lo desconocido;
      `falta_cartas`→`documentos`, `requiere_humano`→`requiere_agente` (mandados por el spec).
- [x] B11.2 Chokepoint único: `_normalize_chatwoot_labels` (app.py, path SQL primario usado
      por app.py y tasks_chatwoot) delega en `_filter_official_labels` → los 3 paths
      (calculado / fallback / sincronizado SQL) quedan alineados al catálogo. Saneaba labels
      fantasma reales de `v_rh_work_queue.suggested_chatwoot_labels` (`requiere_humano`,
      `ubicacion_extranjero`→`foraneo`, `validar_ch`→`requiere_revision_ch`,
      `posible_abandono`→`seguimiento`) que antes llegaban crudas a Chatwoot.
      > Nota: la vista SQL aún define esos nombres en origen; el chokepoint Python los sanea
      > (comportamiento vivo correcto). Renombrarlos en la vista es migración aparte (deploy psql).
- [x] B11.3 Tests en `tests/test_candidate_labels.py`: `test_filter_maps_ghost_alias_to_official`,
      `test_sql_primary_path_maps_ghost_alias`, `test_sql_primary_path_drops_unknown_label`,
      `test_sql_primary_path_parses_pg_array_with_ghost` (+ allowlist existente). 90 verdes.
