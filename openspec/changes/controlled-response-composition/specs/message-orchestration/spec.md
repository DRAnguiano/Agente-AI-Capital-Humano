## ADDED Requirements

### Requirement: La rama del current-turn guard compone el ack con la capa controlada sin alterar la decisión

El sistema SHALL ensamblar el contrato `ResponseComposition` y componer el prefijo
del ack en la rama del current-turn guard del worker (donde `build_current_turn_ack`
produce la respuesta que sobrescribe la del orquestador), después de que el escritor
único de facts `_store_lead_memory_updates` ya persistió los `pre_validated_facts`
del turno. El sistema MUST conservar intactas todas las decisiones operacionales
—pregunta pendiente canónica, etiquetas, estado del funnel, elegibilidad y
handoff— y MUST NOT permitir que la capa lingüística las modifique. El sistema MUST
NOT introducir un segundo escritor de facts ni un segundo prefijo de ack: el
composer solo decora el prefijo único existente. La pregunta pendiente canónica MUST
seguir proviniendo de `build_current_turn_ack` / `next_question_from_missing_facts`.

#### Scenario: La capa lingüística no altera labels ni estado
- **WHEN** el guard delega la redacción del prefijo del ack a la capa controlada
- **THEN** los labels, el `funnel_stage` y la persistencia del turno son idénticos a los de la ruta determinista
- **AND** solo cambia el texto de cortesía que precede a la pregunta canónica

#### Scenario: La persistencia precede a la composición y no se añade un escritor
- **WHEN** el guard compone el ack tras `_store_lead_memory_updates`
- **THEN** los facts del turno ya están persistidos por el escritor único
- **AND** el composer no ejecuta ninguna escritura adicional de facts

#### Scenario: Fallback no degrada el contrato operacional
- **WHEN** la capa lingüística falla y se usa el ack determinista
- **THEN** la respuesta y las decisiones operacionales son las mismas que hoy
- **AND** no se introduce ninguna regresión en el flujo del funnel
