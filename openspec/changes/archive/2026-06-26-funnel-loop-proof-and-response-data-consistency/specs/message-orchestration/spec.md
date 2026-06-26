## ADDED Requirements

### Requirement: Saludo único en primer contacto con pregunta embebida

En el primer contacto, cuando el mensaje del candidato trae una pregunta embebida (p. ej. "hola, me interesa la vacante, ¿qué necesito?"), la respuesta ensamblada SHALL contener el intro de saludo de Mundo **una sola vez**. El sistema MUST NOT concatenar la respuesta a la pregunta (que ya saluda) con el `GREETING_REPLY` completo (que vuelve a saludar): el nudge del funnel para un candidato sin nombre debe ser solo la pregunta del siguiente dato, sin repetir el intro.

#### Scenario: Primer mensaje con saludo y pregunta
- **WHEN** un candidato nuevo escribe "Hola buen día, me interesa la vacante, ¿qué necesito para que me contraten?"
- **THEN** la respuesta incluye el intro "Hola, soy Mundo del equipo de reclutamiento de Transmontes…" exactamente una vez
- **AND** cierra con una sola pregunta del funnel (p. ej. el nombre), sin un segundo bloque de saludo

#### Scenario: Nudge del funnel tras responder la pregunta embebida
- **WHEN** la respuesta a la pregunta embebida ya contiene el saludo y el sistema agrega el nudge del siguiente dato
- **THEN** el nudge es solo la pregunta faltante, no el `GREETING_REPLY` con intro

### Requirement: Respuesta de primer contacto concisa

La respuesta de primer contacto SHALL ser concisa y MUST NOT repetir la misma promesa (p. ej. "nuestro equipo lo contactará") múltiples veces en el mismo mensaje.

#### Scenario: Respuesta de bienvenida verbosa
- **WHEN** se compone la respuesta de primer contacto
- **THEN** la promesa de contacto del equipo aparece a lo sumo una vez
- **AND** el mensaje no repite frases equivalentes de cierre
