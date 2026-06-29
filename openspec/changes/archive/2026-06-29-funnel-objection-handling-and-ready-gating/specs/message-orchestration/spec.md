## ADDED Requirements

### Requirement: Respuesta empática y personalizada ante negativa u objeción de un paso del funnel

El orquestador SHALL responder con un acuse empático y personalizado cuando el
candidato declina, dice no tener, o propone una alternativa a un requisito de un campo
núcleo del funnel (documento laboral, licencia, apto médico, experiencia, etc.), en
lugar de re-preguntar el mismo campo en seco o cerrar la conversación abruptamente.

El acuse MUST:
- Dirigirse al candidato por su **nombre de pila** derivado de `candidate.name`
  (primer token; "Joaquín Ramos" → "Joaquín"); si no hay nombre, omitir el vocativo
  sin fallar.
- Validar empáticamente la situación o la alternativa que el candidato aporta.
- Encuadrar el documento como requisito de **protocolo para su expediente**, sin
  presentarlo como un rechazo.
- Aclarar que **por lo pronto no se le exige** como condición bloqueante.
- Invitar a **retomar el proceso** en cuanto lo suba o resuelva su situación.

El acuse MUST NOT inventar umbrales (p. ej. un mínimo de años de experiencia), MUST
NOT prometer la vacante, y SHALL usar la voz "nuestro equipo" (nunca "Capital
Humano" como tercero). La pregunta de funnel correspondiente NO se repite en el
mismo turno; el sistema MAY marcar el campo como pendiente de envío
(`documents.submission_status = pending_candidate_will_send`, que deriva el label
`seguimiento`) y avanzar al siguiente paso del funnel.

Esta rama SHALL respetar las salidas terminales de dominio: una negativa que implique
no-aptitud (cecati/escuelita/reingreso/B1) cierra el funnel y canaliza, no entra en
esta rama de "retomar cuando suba el documento".

#### Scenario: No tiene cartas pero ofrece una alternativa
- **WHEN** el candidato (nombre "Joaquín Ramos") responde "no tengo cartas laborales, pero tengo videos de mis rutas en TikTok"
- **THEN** la respuesta lo nombra "Joaquín", valida su experiencia comprobable, explica que por protocolo los documentos del expediente deben ser los indicados, aclara que por lo pronto no se le piden como bloqueo, e invita a continuar en cuanto los suba
- **AND** no se repite la pregunta del documento en seco ni se promete la vacante

#### Scenario: Negativa simple a un requisito no bloquea el funnel
- **WHEN** el candidato dice no contar (todavía) con un documento de un paso del funnel, sin implicar no-aptitud
- **THEN** el campo se marca como pendiente de envío (`seguimiento`) y el funnel avanza al siguiente paso en lugar de quedarse en bucle

#### Scenario: Negativa que implica no-aptitud cierra y canaliza
- **WHEN** la negativa corresponde a una salida terminal de dominio (p. ej. sin experiencia en carretera → cecati/escuelita)
- **THEN** se cierra el perfilamiento y se canaliza con acuse específico, en lugar de la rama empática de "retomar cuando suba el documento"

#### Scenario: Sin nombre conocido, omite el vocativo
- **WHEN** el candidato objeta un requisito y aún no se conoce `candidate.name`
- **THEN** el acuse mantiene el tono empático pero sin nombre de pila, sin texto roto ni placeholder

### Requirement: Una no-respuesta de vencimiento se trata como dato faltante y no como confirmación de vigencia

El orquestador MUST NOT confirmar un documento como vigente ni eco-imprimir el
literal cuando el candidato responde a la pregunta de vencimiento de licencia o apto
médico con una no-respuesta o evasiva (por ejemplo: no sabría decirle, no sé, no me
acuerdo, al rato le digo). El sistema SHALL tratar ese vencimiento como dato
faltante: volver a pedirlo de forma breve, o —si la no-respuesta es una evasiva de
aplazamiento— aplicar la rama empática de objeción (marcar pendiente y avanzar) sin
re-preguntar en seco. Un texto de vencimiento que sí denota una fecha o plazo
(incluido uno aproximado como en dos años) o un estado de vigencia SHALL aceptarse
como válido y MUST NOT meter al candidato en bucle.

#### Scenario: "No sabría decirle" no se confirma como vigente
- **WHEN** el candidato responde al vencimiento del apto médico con "no sabría decirle"
- **THEN** la respuesta NO dice "apto médico vigente (no sabría decirle)" ni eco-imprime el literal, y el vencimiento del apto queda como dato faltante (se vuelve a pedir o se difiere por la rama de objeción)

#### Scenario: Vencimiento aproximado real se acepta
- **WHEN** el candidato responde "se me vence aproximadamente en dos años"
- **THEN** el vencimiento se acepta como válido (no se re-pregunta en bucle) y no se convierte en una fecha exacta inventada
