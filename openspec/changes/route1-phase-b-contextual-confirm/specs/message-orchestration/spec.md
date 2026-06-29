## MODIFIED Requirements

### Requirement: Confirmación contextual de campo del funnel (Route-1 Fase B)
Cuando el candidato responde con una afirmación implícita a una pregunta del funnel (`"Es correcto"`, `"Sí"`, `"Así es"`, etc.) y `resolve_route1` devuelve `status=confirmed` para un campo de su allowlist (`experience.years`, `experience.vehicle_type`, `documents.proof`), el sistema SHALL:
1. Inyectar el hecho confirmado en `active_facts` del funnel nudge del turno actual, de modo que ese campo no se vuelva a preguntar.
2. Reemplazar el comentario amistoso por un ack determinista corto del dato confirmado.
3. Continuar con la siguiente pregunta del funnel (o el cierre si el perfil está completo).

El sistema MUST NOT invocar `_answer_friendly_message` cuando route-1 confirma un campo en ese mismo turno — el ack del dato reemplaza al LLM amistoso.

#### Scenario: Afirmación implícita a pregunta de cartas laborales
- **WHEN** el bot preguntó `documents.proof` en el turno anterior y el candidato responde "Es correcto señor." o equivalente
- **THEN** `resolve_route1` devuelve `status=confirmed, field=documents.proof, value=cartas`
- **THEN** la respuesta al candidato es `"Cartas anotadas. [siguiente pregunta del funnel]"` sin repetir la pregunta de cartas

#### Scenario: Afirmación implícita a pregunta de años de experiencia
- **WHEN** el bot preguntó `experience.years` en el turno anterior y el candidato responde un número
- **THEN** `resolve_route1` devuelve `status=confirmed, field=experience.years, value=N`
- **THEN** la respuesta es `"N años de experiencia, anotado. [siguiente pregunta]"`

#### Scenario: Campo fuera del allowlist de route-1 — sin cambio
- **WHEN** el bot preguntó un campo fuera del allowlist (`license.type`, `medical.apto_status`, `candidate.name`, `candidate.city`)
- **THEN** route-1 devuelve `status=no_persist, reason=field_not_allowed` y el flujo es idéntico al actual

#### Scenario: Negación implícita — sin inyección
- **WHEN** el candidato responde "No señor" o equivalente a una pregunta del funnel
- **THEN** route-1 devuelve `status=no_persist, reason=negation` y el flujo es idéntico al actual (el campo se vuelve a preguntar en el siguiente turno o se maneja por la ruta de clarificación)

## ADDED Requirements

### Requirement: Ack determinista por campo confirmado por route-1
El sistema SHALL tener un mapa de strings de ack por campo del allowlist de route-1. Cada ack SHALL ser breve (máx. 1 oración), confirmar el dato recibido, y no incluir elogios ni promesas de contratación.

#### Scenario: Ack incluye el valor cuando es numérico
- **WHEN** route-1 confirma `experience.years=6`
- **THEN** el ack es `"6 años de experiencia, anotado."` (con el número)

#### Scenario: Ack para documents.proof
- **WHEN** route-1 confirma `documents.proof=cartas`
- **THEN** el ack es `"Cartas anotadas."`
