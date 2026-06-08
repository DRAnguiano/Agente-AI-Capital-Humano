# Tasks — live-reply-grounding-and-quality

> Changeset **doc-only**. Estas tasks describen el trabajo de implementación futuro en bloques
> pequeños; quedan sin marcar hasta que cada bloque se implemente con su test verificable.

## B1. Friendly grounding anti-fabricación (P0)
- [ ] B1.1 Quitar/neutralizar el few-shot "4 años" del prompt de `_answer_friendly_message`
      (`app/orchestrators/knowledge_orchestrator.py`); el comentario no introduce cifras.
- [ ] B1.2 Guard anti-fabricación: si el LLM introduce números/años no presentes en el mensaje
      del candidato, descartar y usar un comentario neutro.
- [ ] B1.3 Test verificable: input "ahorita le respondo" → respuesta sin dígitos ni "años".

## B2. Dominio sencillo/full/escuelita (P0)
- [ ] B2.1 `current_turn.py` + `chatwoot_note_sync.py`: `sencillo` no se etiqueta "(escuelita)".
- [ ] B2.2 Dominio: `sencillo` (rígido 2 ejes) válido y ≠ escuelita; `full` = doble remolque/dolly;
      `torton`/`rabón`/reparto/interurbano → pueden derivar a `escuelita`/CECATI, ≠ full, ≠ sencillo,
      sin "transferencia hacia quinta rueda".
- [ ] B2.3 Test: `vehicle_type=sencillo` → ack/nota sin "escuelita".

## B3. Guard de extracción de edad (P0/P1)
- [ ] B3.1 `profile_extractor.py`: no inferir `candidate.age` desde "N años" de experiencia.
- [ ] B3.2 Test: "llevo 20 años de fullero" → `experience.years`, sin `candidate.age`.

## B4. Higiene de fuentes de conocimiento (P1)
- [ ] B4.1 Auditar `data/00_*`..`data/05_*`: separar instrucción interna de texto respondible.
- [ ] B4.2 Filtro/strip en el prompt de RAG para no devolver instrucciones internas.
- [ ] B4.3 Test: chunk con "Mundo debe..." no aparece en la respuesta final al candidato.

## B5. RAG answer grounding / anti over-retrieval (P1)
- [ ] B5.1 Acotar recuperación/ensamblado a fuentes relacionadas con la pregunta.
- [ ] B5.2 Test: "pago para sencillo" no mezcla paradas autorizadas ni proceso documental.

## B6. Ack dedup en current_turn (P2)
- [ ] B6.1 `build_current_turn_ack` + `next_question_from_missing_facts`: un solo "Perfecto".
- [ ] B6.2 De-dup de facts en el prefijo (no "20 años, 20 años de experiencia").
- [ ] B6.3 Test: ciudad + licencia → un solo prefijo de confirmación, sin fact repetido.

## B7. Cierre de perfil / handoff de llamada (P2)
- [ ] B7.1 Siguiente paso claro al completar perfil o documentos declarados.
- [ ] B7.2 Helper compartido `is_business_hours()` — horario **8:00–17:30 L–V**, zona canónica
      `America/Monterrey`. NO confundir con `followup/ventana.py` (08:30–20:30 L–S, envío async).
- [ ] B7.3 Corregir la rama **en-horario** del cierre (hoy no dice "el equipo puede contactar").
- [ ] B7.4 Estado/label de lead para llamada; `llamada_pendiente` solo tras añadirlo al catálogo.
      No prometer agenda real: "lo dejo registrado para que el equipo te contacte en horario".
- [ ] B7.5 Test: solicitud de llamada en/fuera de horario → mensaje y estado correctos.

## B8. Manejo de correcciones explícitas (P0, mayor)
- [ ] B8.1 Reconocer corrección explícita y sobrescribir sin repetir el valor anterior.
- [ ] B8.2 Cross-reference / jalar adelante tasks de `multi-intent-migration` (6.3, 7.2, 7.4,
      9.3.3, 9.3.11) sin duplicar la lógica.
- [ ] B8.3 Test: "en realidad es sencillo" tras "full" → sencillo, sin escuelita; "10 años"
      tras escuelita → no escuelita.

## B9. Datos sensibles / pagos / trámites con costo (P1)
- [ ] B9.1 El bot no solicita pagos, depósitos, cuentas bancarias, CURP/NSS completos ni
      comprobantes fuera de flujo autorizado; no inventa trámites/costos.
- [ ] B9.2 Trámite con costo / datos sensibles → handoff o "el equipo lo confirma por el canal autorizado".
- [ ] B9.3 Test: pregunta por trámite con costo/cuenta/CURP → no pide datos sensibles, deriva.

## B10. Decisión operativa unificada (P1)
- [ ] B10.1 Respuesta visible, nota interna y labels derivan de la misma decisión por turno
      (Postgres/lead_memory): perfil, intención, horario, llamada, humano, bloqueo.
- [ ] B10.2 Test: último mensaje "5" con campo pendiente experiencia → la nota NO dice
      "preguntó por documentos"; acción/bloqueo/labels consistentes con "registró experiencia".

## B11. Labels oficiales / no labels fantasma (P2)
- [ ] B11.1 Emitir solo labels del catálogo de `chatwoot-label-taxonomy`; `falta_cartas` → `documentos`.
- [ ] B11.2 Alinear labels calculados ↔ sincronizados ↔ catálogo oficial.
- [ ] B11.3 Test: cálculo que proponga `falta_cartas` (u otra fuera de catálogo) no se emite.
