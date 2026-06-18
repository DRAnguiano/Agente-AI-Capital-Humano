# message-orchestration (delta)

## ADDED Requirements

### Requirement: Voz de equipo — no referirse a Capital Humano como tercero

El sistema SHALL responder siempre con voz de equipo (primera persona plural: "nuestro
equipo", "aquí lo revisamos", "llámenos") y SHALL NOT referirse a "Capital Humano" como una
entidad o tercero separado, en cualquier modo de respuesta (plantilla, RAG o LLM amistoso).
Las instrucciones y ejemplos del prompt del sistema SHALL NOT inducir ese uso (sus ejemplos
no deben mostrar "Capital Humano" como tercero).

#### Scenario: Derivación a revisión humana usa voz de equipo
- **WHEN** el sistema deriva un tema a revisión humana o aclara que algo se valida después
- **THEN** la respuesta usa "nuestro equipo" / "aquí lo revisamos" / "llámenos"
- **AND** la respuesta no contiene "Capital Humano" como tercero

#### Scenario: El prompt del sistema no induce "Capital Humano"
- **WHEN** se construye el prompt del LLM (persona y/o contexto RAG)
- **THEN** las instrucciones y ejemplos del prompt no usan "Capital Humano" como tercero separado

### Requirement: Ciclo de vida de la revisión humana

El sistema SHALL NOT salir automáticamente del estado de revisión humana
(`HUMAN_REVIEW_REQUIRED`) por mensajes del candidato. Una conversación en revisión humana
SHALL permanecer en ese estado hasta una acción humana u operativa explícita que la libere,
tras lo cual el procesamiento normal MAY reanudarse. El sistema SHALL NOT dejar la
conversación en un bloqueo permanente sin ninguna vía de liberación.

#### Scenario: Mensaje del candidato no reactiva el bot durante revisión humana
- **WHEN** una conversación está en `HUMAN_REVIEW_REQUIRED` y el candidato envía un mensaje
- **THEN** el sistema mantiene el estado de revisión humana (no auto-reanuda el bot)

#### Scenario: Liberación explícita por acción humana
- **WHEN** un agente u operación libera explícitamente la conversación de la revisión humana
- **THEN** el sistema permite reanudar el procesamiento normal en los turnos posteriores

#### Scenario: No hay bloqueo permanente
- **WHEN** una conversación entra en `HUMAN_REVIEW_REQUIRED`
- **THEN** existe al menos una vía explícita (acción humana/operativa) para liberarla
