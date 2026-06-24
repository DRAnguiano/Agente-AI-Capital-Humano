## ADDED Requirements

### Requirement: Separación de contenido respondible y notas internas

Las fuentes de conocimiento (RAG) SHALL separar el contenido respondible al candidato de las
notas internas/políticas operativas. El texto marcado como interno (instrucciones a "Mundo",
reglas de operación) SHALL NOT recuperarse ni ensamblarse como respuesta final al candidato.

> Nota de implementación: requirement doc-only. La reestructuración de `data/*.md` y el filtro
> en el prompt de RAG quedan para fases posteriores.

#### Scenario: Instrucción interna no se devuelve al candidato
- **WHEN** una fuente contiene "Mundo debe pedir su ciudad o el circuito antes de dar una cifra"
- **THEN** esa instrucción no aparece en la respuesta al candidato
- **AND** la respuesta usa solo el contenido respondible (cifras/condiciones reales)

### Requirement: RAG no decide facts ni mezcla fuentes no relacionadas

El RAG SHALL responder solo políticas/condiciones HR y SHALL NOT decidir facts del candidato.
Ante una pregunta específica, el ensamblado SHALL limitarse a fuentes relacionadas con esa
pregunta y SHALL NOT concatenar chunks de temas no relacionados.

> Nota de implementación: requirement doc-only; consistente con la prioridad de fuentes de
> verdad (turno actual > lead_memory > Neo4j > RAG > LLM).

#### Scenario: Recuperación enfocada por tema
- **WHEN** el candidato pregunta por pago para sencillo
- **THEN** el RAG recupera y ensambla solo contenido de pago/tipo de unidad
- **AND** no incluye paradas autorizadas ni el proceso documental de otra ciudad
