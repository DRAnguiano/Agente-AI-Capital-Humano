## Context

El estado de "perfil completo" hoy vive en tres lugares con criterios distintos:

| Fuente | `experience.years` | documento laboral |
|---|---|---|
| `funnel_state_planner.CORE_FIELDS` (current/next-gen planner) | sí | sí (`documents.proof`) |
| `current_turn.next_question_from_missing_facts` (funnel en producción) | sí (522) | sí (`_has_labor_document`, 524) |
| `chatwoot_note_sync.calculate_candidate_labels` gate `perfil_listo` (392-401) | **no** (vía `has_experience`=vehicle, 329-334) | **no** |

El gate de label es el más laxo y es el que emite `perfil_listo`+`requiere_revision_ch`
hacia Chatwoot. Como `next_question_from_missing_facts` aún tiene preguntas, el bot
marca "listo" y sigue preguntando — exactamente lo visto en conv 123. Existe además
una ruta degradada en `app/app.py:597-613` con el mismo criterio laxo (comentada como
"OJO — ruta DEGRADADA").

Sobre objeciones: hoy `next_question_from_missing_facts` re-pregunta el mismo campo
(p. ej. `residency_document_question`, current_turn.py:524-526) sin reconocer la
negativa ni la alternativa que ofrece el candidato. No hay rama empática.

Sobre vencimientos: `_apto_status` (chatwoot_note_sync.py:14-19) y `_is_vigente`
(142-143) declaran "Vigente" en cuanto existe **cualquier** texto en
`*_expiration_text`, y el confirm de `current_turn.py` eco-imprime ese texto entre
paréntesis. El extractor, además, llega a guardar una no-respuesta cruda
("no sabría decirle") como valor del campo. Resultado (conv 128): "apto médico
vigente (no sabría decirle)" + `perfil_listo` con el apto realmente desconocido. No
hay una noción de "texto de vencimiento válido" que distinga una respuesta real
(fecha/plazo, "vigente", "vencido") de una no-respuesta/evasiva.

## Goals / Non-Goals

**Goals:**
- `perfil_listo` se activa si y solo si el funnel conversacional está agotado (la
  misma condición que produce `_profile_complete_closing`). Una sola fuente de
  verdad para "listo".
- Respuesta empática, personalizada con nombre de pila, ante negativa/alternativa
  en cualquier campo núcleo: valida, encuadra como protocolo de expediente
  diferido, no bloquea, invita a retomar.
- Mantener invariantes de dominio: no inventar mínimos de años, no prometer
  vacante, voz "nuestro equipo", friendly LLM sin preguntas, no-apto cierra funnel.

**Non-Goals:**
- No se rediseña el planner de 6 campos (`funnel_state_planner`); solo se alinea el
  gate de label a la condición real del funnel en producción.
- No se cambia el esquema de facts ni el catálogo de labels.
- No se aborda la agenda de llamada (`llamada_pendiente`) ni el followup scheduler.
- No se crea un clasificador nuevo de "objeción"; se reutiliza la detección de
  negativa/alternativa que ya existe en la extracción de turno.

## Decisions

**D1 — Gate de `perfil_listo` derivado de la condición de funnel agotado.**
En lugar de duplicar predicados, el gate consulta la misma verdad que el funnel:
"no queda siguiente pregunta". Opción preferida: exponer un helper
`profile_funnel_complete(facts) -> bool` en `current_turn.py` (equivalente a
"`next_question_from_missing_facts` devolvería el cierre") y usarlo tanto en
`calculate_candidate_labels` como en la ruta degradada de `app.py`. Mínimo viable
alterno: endurecer el gate añadiendo `experience.years` explícito y
`_has_labor_document(facts)` a la condición (392-401) y separar `has_experience`
del `vehicle_confirmed` para el gate. Se elige el helper compartido para no volver
a divergir.

**D2 — `has_experience` para labels intermedios vs. gate de listo.**
`has_experience` (329-334) seguirá sirviendo para el label `falta_experiencia` /
`documentos` (un candidato con `vehicle_type` ya no "falta experiencia" en sentido
de unidad). Pero el **gate de listo** exige `experience.years` explícito: son dos
preguntas distintas (qué unidad maneja vs. cuántos años). No se colapsan.

**D3 — Rama de objeción empática, determinista en estructura, cálida en copy.**
Cuando el turno trae una negativa o alternativa para el campo que el funnel está
pidiendo (señal ya extraída: `documents.proof in {ninguno…}`, negativa simple,
o mención de prueba alterna), el orquestador emite un acuse con esta forma:
1. Nombre de pila (derivado de `candidate.name`, primer token; "Joaquín Ramos" →
   "Joaquín").
2. Validación empática de lo que el candidato aporta o de su situación.
3. Encuadre de protocolo: el documento es requisito para su expediente.
4. Desbloqueo: "por lo pronto no se lo pedimos como condición".
5. Invitación a retomar: en cuanto lo suba/resuelva, agilizamos su proceso.
El copy lo redacta el LLM friendly bajo estas restricciones (no inventa mínimos,
no promete vacante, voz "nuestro equipo"); la **estructura y el disparo** son
deterministas. La pregunta del funnel NO se repite en seco; si procede, el sistema
puede dejar el campo como "pendiente de subir" (`documents.submission_status =
pending_candidate_will_send` → label `seguimiento`) y avanzar al siguiente paso.

**D4 — Nombre de pila helper compartido.**
`first_name(facts)` normaliza `candidate.name` al primer token capitalizado para
uso natural; tolera nombre vacío (omite el vocativo en vez de fallar).

**D5 — "Texto de vencimiento válido" como predicado, y no-respuesta = faltante.**
Se introduce `is_valid_expiration_text(text) -> bool` (en `current_turn.py`): es
válido un texto que denote una fecha/plazo (reusa la detección de
`_expiry_within_three_months`), o las palabras de estado "vigente"/"al corriente"/
"vencido". Una no-respuesta/evasiva ("no sabría decirle", "no sé", "no me acuerdo",
"al rato le digo", vacío) es **inválida**. Efectos deterministas:
1. La extracción NO persiste un `*_expiration_text` inválido (queda como faltante);
   si llegó por el LLM, se descarta antes de escribir (consistente con el patrón de
   `canonicalize_proof`, que devuelve `None` cuando el valor no es mapeable).
2. `_apto_status`/`_is_vigente` solo devuelven "Vigente" cuando el texto es válido,
   no por mera presencia de caracteres.
3. El confirm-ack NO eco-imprime el literal ni afirma "vigente" sobre texto inválido;
   en su lugar el campo cuenta como faltante → el funnel lo vuelve a pedir, o entra
   la rama de objeción (D3) si la no-respuesta es una evasiva ("al rato le digo").
4. `profile_funnel_complete`/el gate de `perfil_listo` (D1) ya excluyen el caso al
   exigir el dato real, pero MUST validar el vencimiento vía este predicado, no por
   presencia de texto.
No se inventa una fecha exacta a partir de un plazo aproximado ("dos años" se
conserva como plazo, no se convierte a fecha); solo se distingue válido vs.
no-respuesta.

## Risks / Trade-offs

- **Riesgo:** endurecer el gate retrasa `perfil_listo` un turno o dos → menos leads
  marcados "listo" antes de tiempo. Es el comportamiento deseado: el label debe
  reflejar perfil real. Mitigación: el label `seguimiento` cubre el interín.
- **Riesgo:** la rama de objeción podría dejar al candidato en bucle si nunca sube
  el documento. Mitigación: marcar `documents.submission_status` y avanzar el
  funnel; no re-preguntar el mismo campo en seco; el followup scheduler retoma.
- **Trade-off:** copy generado por LLM vs. plantillas fijas. Se elige LLM acotado
  por naturalidad (nombre de pila, empatía situacional) con guardas
  deterministas; las plantillas fijas sonarían robóticas para objeciones variadas.
- **Riesgo:** divergencia futura entre gate y funnel si alguien edita uno solo.
  Mitigación: D1 los une en un helper único; `guard_asked_field.py` ya documenta
  el patrón de "espejo exacto" a mantener.
- **Riesgo (D5):** un validador de vencimiento demasiado estricto rechazaría
  respuestas reales pero informales ("como en dos años", "el próximo diciembre") y
  metería al candidato en bucle. Mitigación: el predicado acepta plazos/fechas
  aproximados y estados ("vigente"/"vencido"); solo rechaza no-respuestas explícitas.
  El conjunto de no-respuestas se mantiene acotado y se cubre con pruebas; ante duda,
  preferir aceptar (la rama de objeción y el followup cubren el interín) sobre
  bloquear, salvo el `perfil_listo`, que sí exige dato válido.
