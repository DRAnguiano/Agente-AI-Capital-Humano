# Design — live-reply-grounding-and-quality

## Contexto

Estas fallas viven en el **camino vivo** (la capa que decide en producción), no en la capa
canónica de `multi-intent-migration` (shadow/offline). En debounce ON, el reply visible lo
compone el **current_turn guard** (`build_current_turn_ack` + `next_question_from_missing_facts`)
y, en otros turnos, el **LLM friendly/RAG** del `knowledge_orchestrator`. Por eso este
changeset es un contrato del camino vivo, separado del rebuild canónico.

## Causa raíz por falla (evidencia)

| Falla | Origen | Evidencia |
|---|---|---|
| Alucina "4 años" | few-shot del prompt friendly | `knowledge_orchestrator.py:456` (ejemplo "4 años") + sin guard anti-fabricación |
| Fuga instrucción de pago | instrucciones internas en fuente RAG | `data/01_pago_prestaciones.md` ("Mundo debe... debe pedir... antes de dar una cifra") |
| Mezcla de temas | RAG over-retrieval | `_answer_rag_message` + `retrieve_preferred_context` sin filtro estricto |
| sencillo→escuelita | hardcode en guard vivo | `current_turn.py:170-174,203`; `chatwoot_note_sync.py:262,299` (contradice `10a.2`/esquema) |
| Edad "20" falsa | extractor de edad agarra experiencia | `profile_extractor.py:257-261` |
| Duplica "Perfecto" | ack + next_question | `current_turn.py:208` + `:162` |
| "20 años, 20 años" | edad falsa + experience.years en el ack | `profile_extractor.py` + `build_current_turn_ack` |
| Correcciones ignoradas | sin capa de corrección | tasks pendientes en `multi-intent-migration` |

## Decisiones

1. **Grounding del friendly**: el comentario corto no debe contener facts no dichos por el
   candidato. Camino: eliminar el few-shot numérico y/o añadir un guard que descarte respuestas
   con cifras/años ausentes del mensaje. No se cambia el rol del LLM (solo reacciona).
2. **Dominio de unidad** (corregido en B0.1): `sencillo` (rígido 2 ejes) = experiencia/vacante
   válida, nunca `escuelita`. `full` = tractocamión con doble remolque unido por
   convertidor/dolly. `torton`, `rabón`, reparto local y servicio interurbano = experiencias en
   unidades de carga que **pueden derivar a valoración `escuelita`/CECATI**; NO se confirman
   como `full`, NO se describen como "transferencia hacia quinta rueda" y NO se tratan como
   `sencillo`. Fuente: `docs/esquema_perfilamiento_v1.md` (§3), `data/02_documentos_requisitos.md`.
3. **Edad explícita**: `candidate.age` solo con señal de edad explícita, nunca desde "N años"
   de experiencia/antigüedad.
4. **Higiene de conocimiento** (capability nueva): el contenido respondible y las notas
   internas deben estar separados en las fuentes; el RAG no devuelve instrucciones internas
   ni decide facts; ensamblado enfocado por tema.
5. **Ack determinista sin duplicación**: un solo prefijo de confirmación y de-dup de facts.
6. **Correcciones**: contrato conversacional aquí; la mecánica de detección/persistencia se
   reusa de `multi-intent-migration` (6.3, 7.2, 7.4, 9.3.x), sin duplicar.
7. **Perfil listo / llamada** (corregido en B0.1/B7.2): horario **8:00–17:30, lunes a viernes**,
   zona canónica **`America/Mexico_City`** (fuente: `app/knowledge/business_hours.py` y
   `current_turn._profile_complete_closing`). La ventana de `followup/ventana.py`
   (08:30–20:30, lunes–sábado) es para **envío async de seguimientos** y NO es el horario
   de oficina. No prometer agenda real inexistente; `llamada_pendiente` ya existe en el
   catálogo de labels, pero falta `call_scheduling` determinista para emitirla y registrar
   `scheduling.call_window_*`.
8. **Datos sensibles** (B0.1): el bot no solicita pagos/depósitos/cuentas/CURP-NSS completos ni
   comprobantes fuera de flujo autorizado; trámites con costo → handoff / canal autorizado.
9. **Decisión operativa unificada** (B0.1): respuesta visible, nota interna y labels derivan de
   la misma decisión por turno (Postgres/lead_memory), sin contradecirse (caso "5" ≠ "preguntó
   por documentos"). Consistente con `postgres-truth-and-label-sync`.
10. **Labels oficiales** (B0.1): solo labels del catálogo de `chatwoot-label-taxonomy`; nada de
    labels fantasma (`falta_cartas` → `documentos`).

## Hallazgo de horario (diagnóstico)

- Decisión de horario en vivo: `app/knowledge/business_hours.py` centraliza
  `is_business_hours()` (`America/Mexico_City`, L–V 8:00–17:30) y
  `current_turn._profile_complete_closing` ya lo usa. La rama **en-horario** sigue
  incompleta (no dice "el equipo puede contactar").
- Dos TZ en el repo: `America/Mexico_City` (closing/horario de oficina) vs `America/Monterrey`
  (`followup/ventana.py` + celery, envío async). Decisión (`core-consistency-fixes`, #15): la
  zona canónica del **horario de oficina/llamada** es `America/Mexico_City` (ya usada por el
  código del check). `ventana.py`/celery permanecen en `America/Monterrey` (dominio distinto,
  ventana 08:30–20:30 L–S; además funcionalmente equivalentes en offset).
- `perfil_listo` real y usado; `llamada_pendiente` existe en el catálogo oficial, pero su
  emisión queda pendiente del flujo `call_scheduling` (`scheduling.call_requested`,
  `scheduling.call_status`, `scheduling.call_window_text`, `scheduling.call_window_valid`);
  `seguimiento_urgente` no existe (no inventarlo).

## Fuera de alcance

- Promover **route1** a productivo (sigue shadow/log-only).
- OCR / document-understanding (solo registro para revisión humana).
- Reescribir la capa canónica de `multi-intent-migration`.
