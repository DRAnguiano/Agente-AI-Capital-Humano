# knowledge-source-hygiene Specification

## Purpose

Garantizar que las fuentes de conocimiento (RAG) entreguen al candidato solo contenido
respondible y enfocado: las instrucciones internas/políticas de operación no se devuelven
como respuesta, el RAG no decide facts del candidato y el ensamblado se acota a las fuentes
relacionadas con la pregunta. Implementado en `app/knowledge/context_builder.py`
(`_strip_internal_instructions`, `_focus_items_by_source`).
## Requirements
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

### Requirement: Emparejamiento de fuente preferida insensible a extensión y ruta

El filtrado por fuente preferida del RAG SHALL casar un `preferred_source`
contra el `source` indexado por su *stem* (basename sin extensión conocida:
`.md`, `.markdown`, `.txt`), independientemente de si uno incluye extensión o
prefijo de ruta y el otro no. Un nombre de fuente sin extensión proveniente del
grafo (Neo4j `coalesce(filename, id)`) MUST seleccionar el contenido indexado
con extensión. El sistema MUST NOT devolver `NO_CONTEXT_REPLY` por una pregunta
que sí tiene fuente autorizada y contenido por encima del umbral de score,
cuando la única discrepancia es la extensión del nombre de fuente.

El emparejamiento MUST conservar el aislamiento por fuente: un item entra sólo
si su stem pertenece al conjunto de stems preferidos (allowlist); no se admiten
chunks de fuentes no preferidas.

#### Scenario: Fuente del grafo sin extensión recupera contenido
- **WHEN** el contrato fija `preferred_sources = ["01_pago_prestaciones"]` (sin `.md`) y el candidato pregunta por pago
- **THEN** la recuperación devuelve los chunks de `01_pago_prestaciones.md`
- **AND** la respuesta usa ese contenido en lugar de `NO_CONTEXT_REPLY`

#### Scenario: Fuente con extensión sigue funcionando
- **WHEN** el contrato fija `preferred_sources = ["01_pago_prestaciones.md"]`
- **THEN** la recuperación devuelve los mismos chunks que la variante sin extensión

#### Scenario: No se cuelan fuentes no preferidas
- **WHEN** el contrato fija `preferred_sources = ["01_pago_prestaciones"]`
- **THEN** los items ensamblados provienen únicamente de la fuente cuyo stem es `01_pago_prestaciones`
- **AND** no se incluyen chunks de otras fuentes (p. ej. paradas o proceso documental)

