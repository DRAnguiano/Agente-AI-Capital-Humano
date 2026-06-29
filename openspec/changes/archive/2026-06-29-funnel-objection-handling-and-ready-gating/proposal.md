## Why

Dos problemas observados en producción (conv 123, candidato "Joaquín Ramos",
2026-06-26):

1. **`perfil_listo` se activa antes de que el perfil esté 100% completo.** El gate
   de label en `calculate_candidate_labels` (chatwoot_note_sync.py:392-401)
   considera la experiencia satisfecha solo con `experience.vehicle_type`
   (`has_experience = vehicle_confirmed or experience.years or …`,
   chatwoot_note_sync.py:329-334) y **no** exige documento laboral. Pero el funnel
   conversacional (`next_question_from_missing_facts`, current_turn.py:522-526)
   todavía pregunta `experience.years` y el documento por residencia. Resultado en
   los logs: tras "apto médico vence en seis meses" se marca
   `perfil_listo`+`requiere_revision_ch`, y **acto seguido** el bot sigue
   preguntando "¿Cuántos años de experiencia…?" y "¿Cuenta con cartas laborales o
   semanas del IMSS?". Hay tres definiciones de "listo" desincronizadas
   (funnel_state_planner.CORE_FIELDS, next_question_from_missing_facts, gate de
   label); la del label es la más laxa y dispara prematuro.

2. **No hay manejo empático de negativas/objeciones en los pasos del funnel.**
   Cuando el candidato no tiene un requisito o propone una alternativa ("no tengo
   cartas laborales, pero tengo videos de mis rutas en TikTok"), el bot re-pregunta
   o cierra en seco. Falta una respuesta cálida, personalizada con el nombre de
   pila, que reconozca la situación, explique que es protocolo (los documentos van
   a su expediente), **no** exija el documento de inmediato, e invite a continuar
   en cuanto lo resuelva/suba — sin abandonar al candidato ni alucinar requisitos.

3. **Las no-respuestas de vencimiento se guardan literales y se afirman como
   "vigente".** Observado en prod (conv 128, candidato "David Ramos", 2026-06-27):
   ante "mi apto médico, no sabría decirle", el extractor guardó
   `medical.apto_expiration_text = "no sabría decirle"` (texto crudo de una
   no-respuesta), y el confirm determinista respondió **"apto médico vigente (no
   sabría decirle)"** — porque `_apto_status` (chatwoot_note_sync.py:14-19) trata
   **cualquier** texto no vacío como "Vigente", y el ack de `current_turn.py`
   eco-imprime el literal. Acto seguido marcó `perfil_listo`+`requiere_revision_ch`
   pese a que el apto es desconocido. Mismo patrón (menos dañino) con
   `license.expiration_text = "aproximadamente en dos años"`. Es la misma raíz que
   (1): un dato no validado se cuenta como satisfecho y dispara "listo".

## What Changes

- **Gate de `perfil_listo` alineado a una sola fuente de verdad.** `perfil_listo`
  SHALL activarse únicamente cuando el funnel conversacional está realmente
  agotado: además de unidad/licencia/apto/ciudad, MUST exigir `experience.years`
  explícito (no inferido del `vehicle_type`) y un documento laboral satisfecho
  (`_has_labor_document`/`documents.proof`), de modo que el label nunca preceda a
  la última pregunta del funnel.
- **Respuestas empáticas de objeción por paso del funnel.** Ante una negativa o
  alternativa en cualquier campo núcleo (documento, licencia, apto, experiencia,
  etc.), Mundo SHALL responder de forma cálida y personalizada: usar el nombre de
  pila del candidato de forma natural, validar lo que aporta, explicar que el
  documento es requisito de protocolo para su expediente, aclarar que **por lo
  pronto no se le pide** como bloqueo, e invitar a continuar el proceso en cuanto
  lo suba/resuelva. Sin inventar mínimos (años de experiencia) ni prometer la
  vacante; consistente con la voz "nuestro equipo" (no "Capital Humano" como
  tercero) y con que el LLM friendly nunca pregunta (la pregunta la pone el
  funnel).
- **Validación de los campos de vencimiento (licencia/apto) contra no-respuestas.**
  Una no-respuesta o evasiva ("no sabría decirle", "no sé", "no me acuerdo",
  "al rato le digo") MUST NOT guardarse como un `*_expiration_text` válido ni
  producir un estado "vigente". El sistema SHALL tratar la no-respuesta como **dato
  faltante** (el funnel vuelve a pedir el vencimiento, o aplica la rama empática de
  objeción), y `perfil_listo` MUST NOT activarse mientras el vencimiento de un
  documento núcleo siga siendo una no-respuesta. El confirm NO debe eco-imprimir el
  literal ni afirmar "vigente" sobre un dato no validado.

## Capabilities

### New Capabilities
<!-- ninguna -->

### Modified Capabilities
- `chatwoot-label-taxonomy`: el label `perfil_listo` SHALL gatear sobre el funnel
  realmente completo (incluye `experience.years` explícito y documento laboral),
  no sobre el subconjunto laxo actual; nunca debe coexistir con preguntas de
  funnel pendientes.
- `message-orchestration`: el orquestador SHALL emitir una respuesta empática y
  personalizada (nombre de pila) cuando el candidato declina o propone una
  alternativa a un requisito de un paso del funnel, reconociendo la situación,
  encuadrando el documento como protocolo de expediente diferido e invitando a
  retomar al resolverlo, sin re-preguntar en seco ni alucinar requisitos. Además,
  una no-respuesta a un campo de vencimiento SHALL tratarse como dato faltante y
  NO confirmarse como "vigente" ni eco-imprimirse literal.

## Impact

- Código: `app/chatwoot_note_sync.py` (gate `perfil_listo`, ~392-401; `has_experience`;
  y `_apto_status`/`_is_vigente`, ~14-19/142-143, que hoy declara "Vigente" con
  cualquier texto), `app/app.py:597-613` (ruta degradada con el mismo criterio), y la
  capa de respuesta del funnel (`app/knowledge/current_turn.py` confirm-ack y
  validación de `*_expiration_text` / `app/orchestrators/knowledge_orchestrator.py`)
  para la rama de objeción empática y el rechazo de no-respuestas de vencimiento.
- Comportamiento: `perfil_listo` deja de adelantarse; las negativas reciben acuse
  cálido y accionable en lugar de re-pregunta o cierre seco; las no-respuestas de
  vencimiento ya no se confirman como "vigente" ni se eco-imprimen literales.
- Sin cambios de esquema ni de datos (`data/`). Posible toque a corpus de copy si
  las respuestas de objeción se documentan como plantillas autorizadas.
- Consistente con memorias: voz "nuestro equipo", friendly LLM sin preguntas,
  no-apto cierra funnel, acuse específico en canalización.
