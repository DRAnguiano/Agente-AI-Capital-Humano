# fact-value-canonicalization Specification

## Purpose
TBD - created by archiving change funnel-loop-proof-and-response-data-consistency. Update Purpose after archive.
## Requirements
### Requirement: Canonicalización de `documents.proof` al persistir

Toda escritura de `documents.proof` SHALL normalizar el valor al vocabulario canónico `{"cartas" | "semanas_imss" | "ninguno"}` antes de persistirlo, sin importar la ruta que la origine (extractor determinista, `intent_classifier`, o `answers_to_persist` del LLM). El sistema MUST NOT persistir texto libre (p. ej. `"cartas laborales"`, `"semanas del imss"`) como valor de `documents.proof`, porque los consumidores deterministas (`_has_labor_document`) solo reconocen el vocabulario canónico y un valor no canónico deja el paso documental sin cerrar.

#### Scenario: El LLM devuelve frase libre equivalente a cartas
- **WHEN** el path `answers_to_persist` / `intent_classifier` produce `documents.proof = "cartas laborales"`
- **THEN** el sistema normaliza a `documents.proof = "cartas"` antes de persistir
- **AND** `_has_labor_document(facts)` retorna verdadero y el paso documental se considera satisfecho

#### Scenario: El LLM devuelve frase libre equivalente a semanas IMSS
- **WHEN** el path del LLM produce `documents.proof = "semanas del IMSS"` o `"semanas cotizadas"`
- **THEN** el sistema normaliza a `documents.proof = "semanas_imss"` antes de persistir

#### Scenario: Negación de documentos
- **WHEN** cualquier ruta produce un valor que expresa que el candidato no tiene el documento (p. ej. `"no tengo"`, `"ninguno"`)
- **THEN** el sistema persiste `documents.proof = "ninguno"`

#### Scenario: Valor no mapeable
- **WHEN** una ruta produce un valor que no corresponde a ninguna categoría canónica reconocible
- **THEN** el sistema NO persiste `documents.proof` (lo deja sin determinar) en lugar de guardar el texto crudo

### Requirement: Representación string canónica de `location.is_local_laguna`

El fact `location.is_local_laguna` SHALL persistirse siempre como string canónica `"true"` o `"false"`. Todos los puntos de escritura MUST convertir el resultado booleano de `is_zm_laguna_canonical(...)` a esa string antes de asignarlo, de modo que coincida con la comparación `== "true"` que aplican los consumidores. El sistema MUST NOT almacenar un `bool` crudo de Python en este fact, porque `True == "true"` es falso y la señal se pierde silenciosamente, produciendo divergencia con la etiqueta `local_laguna`.

#### Scenario: Ciudad local computada en current_turn
- **WHEN** se computa `location.is_local_laguna` para una ciudad canónica de la ZM Laguna (p. ej. "Francisco I. Madero")
- **THEN** el fact persistido es la string `"true"`
- **AND** la etiqueta `local_laguna` y el fact coinciden en el mismo turno

#### Scenario: Ciudad foránea
- **WHEN** se computa `location.is_local_laguna` para una ciudad fuera del catálogo (p. ej. "Matehuala")
- **THEN** el fact persistido es la string `"false"`

#### Scenario: Consumidor lee la señal
- **WHEN** un consumidor evalúa `facts.get("location.is_local_laguna") == "true"` para una ciudad local
- **THEN** la comparación es verdadera (la señal no se pierde por diferencia de tipo)

