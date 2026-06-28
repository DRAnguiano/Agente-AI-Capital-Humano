## 1. Fuente única de "funnel completo"

- [ ] 1.1 Exponer `profile_funnel_complete(facts) -> bool` en `app/knowledge/current_turn.py`, equivalente a "`next_question_from_missing_facts` devolvería `_profile_complete_closing()`" (sin texto, solo el predicado). Reutiliza los mismos predicados ya existentes (years explícito + `_has_labor_document`).
- [ ] 1.2 Verificación unitaria del helper: facts con unidad+licencia+apto+ciudad pero SIN years → `False`; con years pero SIN documento → `False`; completo → `True`.

## 2. Endurecer el gate de `perfil_listo`

- [ ] 2.1 En `app/chatwoot_note_sync.py:392-401` reemplazar la condición laxa por `profile_funnel_complete(facts)` (más las exclusiones de no-aptitud ya presentes: `has_non_target_experience`, `has_no_road_experience`, `has_reingreso`).
- [ ] 2.2 Separar el uso de `has_experience` (329-334): sigue alimentando `falta_experiencia`/`documentos`, pero NO satisface el gate de listo (que exige `experience.years` explícito).
- [ ] 2.3 Aplicar el mismo criterio en la ruta degradada `app/app.py:597-613` (usar el helper, no duplicar predicados).
- [ ] 2.4 Confirmar que `perfil_listo` nunca se emite en un turno donde `next_question_from_missing_facts` aún devolvería pregunta (invariante del spec).

## 3. Nombre de pila

- [ ] 3.1 Helper `first_name(facts) -> str` (en `current_turn.py` o util compartida): primer token de `candidate.name`, capitalizado; cadena vacía si no hay nombre.
- [ ] 3.2 Verificar: "Joaquín Ramos" → "Joaquín"; "" → "" (sin fallo).

## 4. Rama de objeción empática

- [ ] 4.1 Detectar en el orquestador (`app/orchestrators/knowledge_orchestrator.py`) que el turno trae negativa/alternativa para el campo que el funnel está pidiendo, reutilizando señales ya extraídas (`documents.proof in {ninguno…}`, negativa simple, mención de prueba alterna). No crear clasificador nuevo.
- [ ] 4.2 Emitir el acuse empático con la estructura D3: nombre de pila + validación + encuadre de protocolo/expediente + "por lo pronto no se lo pedimos" + invitación a retomar. Copy del LLM friendly bajo guardas (sin mínimos inventados, sin prometer vacante, voz "nuestro equipo").
- [ ] 4.3 Marcar el campo como pendiente (`documents.submission_status = pending_candidate_will_send` → label `seguimiento`) y avanzar el funnel al siguiente paso; NO re-preguntar el mismo campo en seco.
- [ ] 4.4 Respetar salidas terminales: si la negativa implica no-aptitud (cecati/escuelita/reingreso/B1), cerrar y canalizar con acuse específico, NO entrar en la rama de "retomar".

## 5. Validación de texto de vencimiento (no-respuesta = faltante)

- [ ] 5.1 Helper `is_valid_expiration_text(text) -> bool` en `app/knowledge/current_turn.py`: válido si denota fecha/plazo (reusa la detección de `_expiry_within_three_months`) o estado ("vigente"/"al corriente"/"vencido"/"vencida"); inválido para no-respuestas/evasivas (`"no sabría decirle"`, `"no sé"`, `"no me acuerdo"`, `"al rato le digo"`, vacío). Lista de no-respuestas acotada y normalizada (`normalize_text`).
- [ ] 5.2 En la escritura de facts (extracción/`_store_lead_memory_updates` o el punto donde se persiste `*_expiration_text`): NO persistir un `license.expiration_text`/`medical.apto_expiration_text` inválido (queda faltante), análogo a `canonicalize_proof` devolviendo `None`.
- [ ] 5.3 `_apto_status`/`_is_vigente` (chatwoot_note_sync.py:14-19, 142-143): devolver "Vigente" solo si el texto es válido por `is_valid_expiration_text`, no por presencia de caracteres.
- [ ] 5.4 Confirm-ack de `current_turn.py`: NO eco-imprimir el literal ni afirmar "vigente" cuando el texto es inválido; tratar el campo como faltante (vuelve a pedir el vencimiento) o derivar a la rama de objeción (sección 4) si es evasiva.
- [ ] 5.5 El gate de `perfil_listo`/`profile_funnel_complete` (D1) MUST validar el vencimiento de documentos núcleo vía `is_valid_expiration_text`, no por presencia de texto.
- [ ] 5.6 Unitarias: `is_valid_expiration_text` (válidos: "en dos años", "vence en 3 meses", "vigente", "vencido"; inválidos: "no sabría decirle", "", "al rato le digo"); y que un apto con texto inválido NO produce "Vigente" ni satisface el gate.

## 6. Verificación (runtime, end-to-end)

- [ ] 6.1 Reproducir la conv de Joaquín vía `POST /orchestrate/message` (canal `api`, user único): tras "apto médico vence en seis meses" con unidad/licencia/apto/ciudad pero sin years ni documento → NO `perfil_listo`; el bot pregunta años.
- [ ] 6.2 Completar years + documento → `perfil_listo`+`requiere_revision_ch` aparecen exactamente cuando el funnel ya no tiene pregunta.
- [ ] 6.3 Objeción: enviar "no tengo cartas laborales, pero tengo videos de mis rutas en TikTok" con `candidate.name="Joaquín Ramos"` → respuesta nombra "Joaquín", valida, encuadra protocolo/expediente, no exige, invita a retomar; sin re-pregunta seca ni promesa de vacante.
- [ ] 6.4 Objeción sin nombre conocido → tono empático sin vocativo, sin placeholder roto.
- [ ] 6.5 Negativa de no-aptitud (sin experiencia en carretera) → cierra y canaliza, no entra en rama de "retomar".
- [ ] 6.6 Regresión: un flujo completo "feliz" sigue marcando `perfil_listo` correctamente.
- [ ] 6.7 Reproducir la conv 128: con apto pendiente, responder "mi apto médico, no sabría decirle" → la respuesta NO afirma "apto médico vigente (no sabría decirle)" ni eco-imprime el literal; el campo queda faltante (vuelve a pedir el vencimiento) y NO se marca `perfil_listo`.
- [ ] 6.8 Vencimiento real informal: "se me vence aproximadamente en dos años" → SÍ se acepta como válido (no entra en bucle), sin convertirlo a fecha exacta.
- [ ] 6.9 `docker compose build worker api && docker compose up -d worker api` (worker horneado; api bind-mount).
- [ ] 6.10 `openspec validate funnel-objection-handling-and-ready-gating --strict`.
