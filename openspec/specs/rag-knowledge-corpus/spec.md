# rag-knowledge-corpus Specification

## Purpose

Corpus de conocimiento RAG (`data/*.md`) alineado al dominio canónico: vocabulario de tracto
full/sencillo (quinta rueda solo jerga), vigencia >3 meses, documento laboral por residencia,
rutas del corredor y jerga del oficio. Los ids de fuente del grafo casan con el nombre de
archivo que indexa Chroma.

## Requirements

### Requirement: Vocabulario canónico de unidad en corpus y copy

El contenido del sistema SHALL referirse a la vacante como "operador de tracto
full o sencillo" en todo el corpus `data/`, saludos, plantillas de seguimiento,
ejemplos de persona y nodos de jerga en Neo4j. "Quinta rueda" y sus variantes
(5ta rueda, quinta, tráiler, tracto, tractocamión) SHALL tratarse únicamente
como jerga de comprensión que indica experiencia compatible, y NUNCA como un
tipo de unidad ni como sinónimo de `full`.

#### Scenario: Saludo no induce jerga ambigua
- **WHEN** el bot se presenta o hace seguimiento de primer contacto
- **THEN** menciona "operador de tracto full o sencillo" y no "operador de quinta rueda"

#### Scenario: Jerga detectada pide aclaración de unidad
- **WHEN** el candidato dice "manejo quinta rueda"
- **THEN** el contenido orienta a preguntar "¿maneja tracto full o sencillo?" sin registrar unidad

#### Scenario: Neo4j no mapea quinta rueda a full
- **WHEN** se consulta el catálogo de jerga sembrado en Neo4j
- **THEN** ningún nodo tiene `quinta rueda`/`quinta`/`tracto` como alias de `full`

### Requirement: Vigencia mínima documentada de 3 meses

El corpus y el copy SHALL indicar "más de 3 meses" como vigencia mínima de
licencia federal y apto médico (regla oficial 2C.0c). La regla de 6 meses queda
derogada.

#### Scenario: Requisitos citan 3 meses
- **WHEN** el candidato pregunta por requisitos
- **THEN** la respuesta indica licencia y apto con más de 3 meses de vigencia

### Requirement: Documento laboral según residencia

El corpus SHALL documentar el requisito laboral condicionado a la residencia:
candidato foráneo → al menos 2 cartas laborales membretadas; candidato local
(Zona Metropolitana de La Laguna: Torreón, Gómez Palacio, Lerdo, Matamoros) →
cartas laborales o documento de semanas cotizadas del IMSS.

#### Scenario: Local con semanas IMSS
- **WHEN** un candidato de Torreón pregunta si puede aplicar sin cartas
- **THEN** se le indica que su documento de semanas cotizadas del IMSS es válido

#### Scenario: Foráneo requiere cartas membretadas
- **WHEN** un candidato foráneo pregunta por el requisito documental laboral
- **THEN** se le piden al menos 2 cartas laborales membretadas

### Requirement: Apoyo de traslado solo para foráneos

El corpus SHALL condicionar explícitamente el boleto de autobús, hospedaje y
comedor subsidiado a candidatos foráneos. A un candidato local de la ZM de La
Laguna solo se le da información de patios y del proceso en Torreón.

#### Scenario: Local no recibe oferta de boleto
- **WHEN** un candidato que ya confirmó residir en Torreón pregunta por rutas o proceso
- **THEN** la respuesta no ofrece boleto de autobús ni hospedaje

### Requirement: Fallback telefónico restringido

El corpus SHALL instruir que la referencia "llámenos de 8:00 a 17:30" se usa solo
cuando el dato no está documentado en la base o requiere confirmación final de
Capital Humano. Si la información existe documentada, se responde con ella
primero. Los datos ya proporcionados por el candidato (p. ej. ciudad) NO SHALL
volver a pedirse.

#### Scenario: Pago con ciudad conocida
- **WHEN** un candidato cuya ciudad ya está registrada pregunta cuánto pagan
- **THEN** la respuesta usa las referencias documentadas del tabulador sin volver a pedir la ciudad

### Requirement: Flujo de precalificación único

El corpus SHALL documentar un único flujo progresivo alineado al funnel:
(1) ciudad, (2) tipo de unidad (tracto full o sencillo), (3) tipo y vigencia de
licencia federal, (4) apto médico, (5) años de experiencia, (6) documento laboral
según residencia, (7) edad. El RFC y el resto del expediente se solicitan después
de la precalificación, cuando el proceso avanza.

#### Scenario: RFC fuera de la precalificación
- **WHEN** el candidato pregunta qué necesita para iniciar
- **THEN** la respuesta no exige RFC; lo menciona como documento posterior del expediente
