## ADDED Requirements

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
