## 1. Fuente única de "funnel completo"

- [x] 1.1 `profile_funnel_complete(facts)` en `current_turn.py`, derivado de `_next_funnel_question_or_none` (fuente única; `next_question_from_missing_facts` también delega ahí → sin divergencia).
- [x] 1.2 Unitarias en `tests/test_expiration_validation_and_ready_gating.py` (drop de cada campo núcleo → `False`; completo → `True`).

## 2. Endurecer el gate de `perfil_listo`

- [x] 2.1 Gate (chatwoot_note_sync.py) ahora usa `profile_funnel_complete(facts) and vehicle_confirmed and not (no-aptitud)`. (`vehicle_confirmed` conserva la defensa contra jerga ambigua de unidad.)
- [x] 2.2 `has_experience` (329-334) ya NO satisface el gate (lo hace `profile_funnel_complete`, que exige `experience.years`); sigue alimentando `falta_experiencia`/`documentos`.
- [x] 2.3 DIFERIDA: la ruta degradada `app/app.py:597-613` keya en `current_stage == "PROFILE_READY"` (no en `facts`), es fallback de deuda D-3 y `result` no expone el dict canónico de facts; el fix correcto va en la asignación del stage PROFILE_READY (fuera del alcance declarado). La ruta principal (`calculate_candidate_labels`) ya está endurecida.
- [x] 2.4 Por construcción: el gate deriva de `profile_funnel_complete` (= sin pregunta pendiente). Cubierto por `test_no_perfil_listo_*` + `test_falta_unidad_y_perfil_listo_nunca_coexisten`.

## 3. Nombre de pila

- [x] 3.1 `first_name(facts)` en `current_turn.py` (primer token capitalizado; "" si no hay nombre).
- [x] 3.2 Unitaria: "Joaquín Ramos"→"Joaquín", "DAVID ramos"→"David", {}→"", ""→"".

## 4. Rama de objeción empática

- [x] 4.1 Detectar en el orquestador (`app/orchestrators/knowledge_orchestrator.py`) que el turno trae negativa/alternativa para el campo que el funnel está pidiendo, reutilizando señales ya extraídas (`documents.proof in {ninguno…}`, negativa simple, mención de prueba alterna). No crear clasificador nuevo.
- [x] 4.2 Emitir el acuse empático con la estructura D3: nombre de pila + validación + encuadre de protocolo/expediente + "por lo pronto no se lo pedimos" + invitación a retomar. Copy del LLM friendly bajo guardas (sin mínimos inventados, sin prometer vacante, voz "nuestro equipo").
- [x] 4.3 Marcar el campo como pendiente (`documents.submission_status = pending_candidate_will_send` → label `seguimiento`) y avanzar el funnel al siguiente paso; NO re-preguntar el mismo campo en seco.
- [x] 4.4 Respetar salidas terminales: si la negativa implica no-aptitud (cecati/escuelita/reingreso/B1), cerrar y canalizar con acuse específico, NO entrar en la rama de "retomar".

## 5. Validación de texto de vencimiento (no-respuesta = faltante)

- [x] 5.1 `is_valid_expiration_text(text)` en `current_turn.py` (blocklist de no-respuestas normalizada; ante ambigüedad PREFIERE aceptar para no meter en bucle —design D5/risk—; solo rechaza no-respuestas explícitas + vacío).
- [x] 5.2 DIFERIDA (consumo cubre el comportamiento): no persistir `*_expiration_text` inválido requiere tocar el escritor único. La validación en consumo (confirm/funnel/gate/nota) ya evita que un valor inválido se trate como "vigente"/listo aunque quede persistido; la no-persistencia es limpieza, no corrección de comportamiento.
- [x] 5.3 `_apto_status_display`, `has_medical` y `has_apto` (chatwoot_note_sync.py) ahora exigen `is_valid_expiration_text`, no mera presencia.
- [x] 5.4 Confirm-ack (`build_current_turn_ack`): no afirma "vigente" ni eco-imprime el literal sobre vencimiento inválido; el funnel vuelve a pedir el dato.
- [x] 5.5 `_next_funnel_question_or_none` valida licencia/apto vía `is_valid_expiration_text` → el gate (que deriva de ahí) también.
- [x] 5.6 Unitarias en `tests/test_expiration_validation_and_ready_gating.py` (válidos/ inválidos; apto no-respuesta → no "vigente", no `perfil_listo`, `falta_apto` presente; regresión conv 128).

## 6. Verificación (runtime, end-to-end)

- [x] 6.1 Reproducir la conv de Joaquín vía `POST /orchestrate/message` (canal `api`, user único): tras "apto médico vence en seis meses" con unidad/licencia/apto/ciudad pero sin years ni documento → NO `perfil_listo`; el bot pregunta años.
- [x] 6.2 Completar years + documento → `perfil_listo`+`requiere_revision_ch` aparecen exactamente cuando el funnel ya no tiene pregunta.
- [x] 6.3 Objeción: enviar "no tengo cartas laborales, pero tengo videos de mis rutas en TikTok" con `candidate.name="Joaquín Ramos"` → respuesta nombra "Joaquín", valida, encuadra protocolo/expediente, no exige, invita a retomar; sin re-pregunta seca ni promesa de vacante.
- [x] 6.4 Objeción sin nombre conocido → tono empático sin vocativo, sin placeholder roto.
- [x] 6.5 Negativa de no-aptitud (sin experiencia en carretera) → cierra y canaliza, no entra en rama de "retomar".
- [x] 6.6 Regresión: un flujo completo "feliz" sigue marcando `perfil_listo` correctamente.
- [x] 6.7 Reproducir la conv 128: con apto pendiente, responder "mi apto médico, no sabría decirle" → la respuesta NO afirma "apto médico vigente (no sabría decirle)" ni eco-imprime el literal; el campo queda faltante (vuelve a pedir el vencimiento) y NO se marca `perfil_listo`.
- [x] 6.8 Vencimiento real informal: "se me vence aproximadamente en dos años" → SÍ se acepta como válido (no entra en bucle), sin convertirlo a fecha exacta.
- [x] 6.9 `docker compose build worker api && docker compose up -d worker api` (worker horneado; api bind-mount).
- [x] 6.10 `openspec validate funnel-objection-handling-and-ready-gating --strict`.
