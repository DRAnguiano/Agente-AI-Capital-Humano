## ADDED Requirements

### Requirement: Residencia local/foránea derivada de una fuente única

El sistema SHALL derivar la residencia (local ZM Laguna vs foráneo) exclusivamente desde el catálogo ZM Laguna mediante `is_zm_laguna_canonical`, exponiéndola como el fact canónico `location.is_local_laguna`. Ningún módulo SHALL usar listas de ciudades hardcodeadas paralelas (`LOCAL_LAGUNA`, `_LOCAL_LAGUNA`) para decidir residencia.

#### Scenario: Ciudad con alias coloquial reconocido por el catálogo
- **WHEN** el candidato dice ser de "Chávez" (alias de Francisco I. Madero en el catálogo de comarca ampliada)
- **THEN** `location.is_local_laguna` se resuelve a `true`
- **AND** tanto la nota IA como el reply al candidato lo tratan como local (no foráneo)

#### Scenario: Listas legacy eliminadas
- **WHEN** se evalúa residencia en cualquier ruta (funnel, orquestador, nota)
- **THEN** la decisión proviene de `is_zm_laguna_canonical` / `location.is_local_laguna`
- **AND** no existe ninguna referencia activa a `LOCAL_LAGUNA` ni `_LOCAL_LAGUNA` como fuente de residencia

### Requirement: El LLM no infiere residencia

El reply generado por la ruta RAG/LLM SHALL NOT inferir o afirmar la residencia (local/foráneo) a partir del nombre crudo de la ciudad. El LLM SHALL recibir la residencia ya resuelta como señal determinista, o tener prohibido afirmar residencia cuando la señal no está disponible.

#### Scenario: Pregunta informativa con ciudad local en el mismo mensaje
- **WHEN** el candidato escribe "soy de Chávez, ¿cuánto pagan?" y el guard se suprime por la pregunta embebida
- **THEN** el reply RAG/LLM NO afirma "se considera foráneo"
- **AND** si menciona documentos por residencia, usa la señal `location.is_local_laguna=true` (trato local)

#### Scenario: Residencia no resuelta
- **WHEN** la ciudad no está en el catálogo y `location.is_local_laguna` no está determinado
- **THEN** el LLM NO afirma que el candidato es foráneo ni local
- **AND** difiere la clasificación de documentos a la confirmación del equipo

### Requirement: Coherencia entre nota, labels y reply

Para un mismo turno, la residencia reflejada en la nota IA, en los labels de Chatwoot y en el reply al candidato SHALL ser idéntica.

#### Scenario: Nota local y reply local
- **WHEN** la nota IA aplica el label `local_laguna`
- **THEN** el reply al candidato NO contradice ese estado tratándolo como foráneo
