## ADDED Requirements

### Requirement: `perfil_listo` gatea sobre el funnel realmente completo

El label `perfil_listo` (y su par `requiere_revision_ch`) SHALL activarse si y solo
si el funnel conversacional de perfilamiento está agotado para ese candidato: además
de unidad confirmada, licencia, apto médico y ciudad, MUST exigir `experience.years`
de forma explícita (no inferida de `experience.vehicle_type`) y un documento laboral
satisfecho (`documents.proof`/`_has_labor_document`). El gate MUST derivarse de la
misma condición que produce el cierre del funnel, de modo que `perfil_listo` nunca
coexista con una pregunta de funnel pendiente.

El label intermedio `falta_experiencia` SHALL seguir reflejando la ausencia de
unidad/experiencia declarada (donde `experience.vehicle_type` basta), pero ese
criterio MUST NOT por sí solo satisfacer el gate de `perfil_listo`.

El estado "Vigente" de licencia/apto (y su contribución al gate de `perfil_listo`)
SHALL derivarse de un **texto de vencimiento válido** (una fecha/plazo, o un estado
"vigente"/"al corriente"/"vencido"), no de la mera presencia de cualquier texto en
`license.expiration_text`/`medical.apto_expiration_text`. Una no-respuesta o evasiva
("no sabría decirle", "no sé", "al rato le digo") MUST NOT contar como vencimiento
satisfecho ni como "Vigente".

#### Scenario: Unidad declarada pero sin años ni documento no marca listo
- **WHEN** el candidato confirmó `experience.vehicle_type` (p. ej. "full"), licencia, apto y ciudad, pero aún no dio `experience.years` ni un documento laboral
- **THEN** NO se aplica `perfil_listo` ni `requiere_revision_ch`
- **AND** el funnel sigue preguntando los años de experiencia / el documento

#### Scenario: Funnel agotado marca listo una sola vez
- **WHEN** el candidato completó unidad, licencia, apto, ciudad, `experience.years` explícito y un documento laboral satisfecho
- **THEN** se aplican `perfil_listo` y `requiere_revision_ch`
- **AND** no queda ninguna pregunta de funnel pendiente en el mismo turno

#### Scenario: `perfil_listo` no coexiste con pregunta pendiente
- **WHEN** el sistema computa labels y `next_question_from_missing_facts` aún devolvería una pregunta de funnel
- **THEN** `perfil_listo` NO está presente en el conjunto de labels emitido

#### Scenario: No-respuesta de vencimiento no cuenta como vigente ni marca listo
- **WHEN** el candidato responde al vencimiento del apto con una no-respuesta (p. ej. "no sabría decirle") y por lo demás tendría el perfil completo
- **THEN** el apto NO se considera "Vigente", NO se aplica `perfil_listo` ni `requiere_revision_ch`, y el vencimiento del apto sigue contando como dato faltante
