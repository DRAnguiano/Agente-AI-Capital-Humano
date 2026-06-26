## ADDED Requirements

### Requirement: El catálogo es la fuente única para todas las rutas de respuesta

El catálogo ZM Laguna (`zm_laguna_localities.json` vía `geo_utils`) SHALL ser la única fuente de residencia consumida por labels, nota IA, funnel, orquestador y reply al candidato. Ninguna ruta de respuesta SHALL usar una lista de ciudades paralela ni inferencia del LLM para decidir residencia.

#### Scenario: Alias de comarca ampliada tratado como local en todas las rutas
- **WHEN** el candidato es de un alias del catálogo (p. ej. "Chávez" → Francisco I. Madero)
- **THEN** labels, nota y reply lo tratan como local de forma consistente

#### Scenario: Sin listas hardcodeadas residuales
- **WHEN** se audita el código de decisión de residencia
- **THEN** no quedan referencias activas a `LOCAL_LAGUNA` ni `_LOCAL_LAGUNA` como fuente de residencia
