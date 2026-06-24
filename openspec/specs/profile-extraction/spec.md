# profile-extraction Specification

## Purpose

Extraer los datos de perfil del candidato a partir de sus mensajes, con una sola fuente
por tipo de dato y una prioridad clara de fuentes de verdad. Neo4j resuelve geografía y
tipo de vehículo; `app/lead_memory/profile_extractor.py` resuelve por regex licencia,
apto médico, experiencia, documentos y edad. Los facts resultantes alimentan
`rh_lead_facts_v2`.

> Nota: el extractor por **regex** es la implementación **baseline actual (deuda técnica)**.
> Sus reglas de negocio se auditarán y migrarán a catálogos/grafo/planners declarativos
> (ver `multi-intent-migration` §13 — auditoría de regex/if de negocio).
## Requirements
### Requirement: Extractor único por tipo de dato

El sistema SHALL extraer ciudad, estado y tipo de vehículo desde nodos `GeoArea` /
`VehicleType` de Neo4j, y licencia, apto médico, experiencia, documentos y edad desde el
extractor regex. No SHALL existir lógica de extracción duplicada fuera de estas dos
fuentes; `current_turn.extract_current_turn_facts` es un wrapper delgado sobre el
extractor regex.

#### Scenario: Ciudad/vehículo
- **WHEN** el mensaje contiene una ciudad o tipo de vehículo reconocible
- **THEN** el fact se resuelve vía Neo4j (con sus aliases y confidence), no por regex ad-hoc

#### Scenario: Licencia/apto/experiencia/documentos/edad
- **WHEN** el mensaje contiene uno de esos datos
- **THEN** el fact se extrae con el extractor regex único y se normaliza a su clave canónica

### Requirement: Prioridad de fuentes de verdad

Al determinar un fact, el sistema SHALL respetar la prioridad: turno actual > lead_memory
> Neo4j > RAG/ChromaDB > generación LLM. El RAG NUNCA SHALL decidir un fact de perfil del
candidato.

#### Scenario: Conflicto entre turno actual y memoria previa
- **WHEN** el dato afirmado en el turno actual contradice un fact previo
- **THEN** prevalece el dato del turno actual

#### Scenario: RAG no fija facts
- **WHEN** una respuesta RAG menciona datos del candidato
- **THEN** esos datos no se persisten como facts; el RAG solo responde políticas/HR

### Requirement: Merge y persistencia de facts

Los facts de Neo4j y del extractor regex SHALL fusionarse en
`_store_lead_memory_updates` y persistirse en `rh_lead_facts_v2` como pares
`fact_group.fact_key = value`, marcando los facts activos del lead.

#### Scenario: Facts extraídos en un turno
- **WHEN** un turno produce facts desde Neo4j y/o regex
- **THEN** se fusionan y se escriben en `rh_lead_facts_v2`, quedando disponibles para el funnel y el status del lead

### Requirement: La edad no se infiere de años de experiencia

El extractor de perfil SHALL NOT inferir `candidate.age` a partir de expresiones de
experiencia o antigüedad ("20 años de fullero", "llevo 20 años manejando"). La edad SHALL
extraerse solo ante una señal explícita de edad (p. ej. "tengo 35 años de edad").

> Nota de implementación: requirement doc-only; el ajuste del regex de edad en
> `profile_extractor.py` queda para una fase posterior.

#### Scenario: Años de experiencia no producen edad
- **WHEN** el candidato dice "llevo más de 20 años de fullero"
- **THEN** el extractor puede registrar experiencia (`experience.years`)
- **AND** no registra `candidate.age`

#### Scenario: Edad explícita sí se registra
- **WHEN** el candidato dice "tengo 35 años de edad"
- **THEN** el extractor registra `candidate.age=35`

### Requirement: Dominio de unidad — sencillo, full, torton/rabón/reparto y escuelita

El sistema SHALL tratar `sencillo` (camión rígido de dos ejes / vehículo de carga mediano)
como experiencia/vacante válida y SHALL NOT convertirlo en `escuelita`. El sistema SHALL
tratar `full` (tractocamión con doble remolque unido mediante convertidor/dolly) como
experiencia objetivo para la vacante full. `torton`, `rabón`, reparto local y servicio
interurbano son experiencias en unidades de carga que pueden derivar a valoración
`escuelita`/CECATI; el sistema SHALL NOT confirmarlas como experiencia `full`, SHALL NOT
describirlas como "transferencia hacia quinta rueda" y SHALL NOT tratarlas como `sencillo`.
Estas categorías SHALL mantenerse distintas entre sí, según
`docs/esquema_perfilamiento_v1.md` (§3) y `data/02_documentos_requisitos.md`.

> Nota de implementación: requirement doc-only; alinea el camino vivo
> (`current_turn.py`, `chatwoot_note_sync.py`) a la fuente de verdad.

#### Scenario: "manejo sencillo" → sencillo, no escuelita
- **WHEN** el candidato dice "manejo sencillo"
- **THEN** el sistema registra `experience.vehicle_type=sencillo`
- **AND** no aplica `escuelita`

#### Scenario: "manejo full" → full
- **WHEN** el candidato dice "manejo full"
- **THEN** el sistema registra `experience.vehicle_type=full`

#### Scenario: "manejo torton" → puede derivar a escuelita/CECATI, no full
- **WHEN** el candidato dice "manejo torton"
- **THEN** el sistema puede derivar a valoración `escuelita`/CECATI
- **AND** no confirma `full` ni lo describe como "transferencia hacia quinta rueda"

#### Scenario: "rabón y reparto local" → puede derivar a escuelita/CECATI, no full ni sencillo
- **WHEN** el candidato dice "manejo rabón y reparto local"
- **THEN** el sistema puede derivar a valoración `escuelita`/CECATI
- **AND** no confirma `full` ni `sencillo` salvo que el candidato diga explícitamente "sencillo"

#### Scenario: Corrección "no quiero escuelita, manejo sencillo"
- **WHEN** el candidato dice "no quiero escuelita, manejo sencillo"
- **THEN** el sistema reconoce la corrección y registra `experience.vehicle_type=sencillo`
- **AND** no mantiene ni repite `escuelita`

### Requirement: Captura de vencimientos en fecha o tiempo relativo

El extractor SHALL capturar el vencimiento de licencia y apto médico expresado
como fecha ("31 de diciembre de 2027", "12/2027") o tiempo relativo ("en 2
años", "como en 6 meses", "el año que entra"), persistiendo
`license.expiration_text` / `medical.apto_expiration_text` y, cuando sea
interpretable, una fecha normalizada. Sin fecha clara NO SHALL inferirse
vigencia suficiente (límite 2B.1).

#### Scenario: Fecha explícita
- **WHEN** el candidato dice "mi licencia vence el 31 de diciembre de 2027"
- **THEN** se persiste `license.expiration_text="31 de diciembre de 2027"`

#### Scenario: Tiempo relativo
- **WHEN** el candidato dice "el apto se me vence como en dos meses"
- **THEN** se persiste `medical.apto_expiration_text` y el planner detecta vencimiento <3 meses

### Requirement: Edad como dato temprano del perfil

El extractor SHALL capturar `candidate.age` desde respuestas a la pregunta de
edad y el planner SHALL evaluar el descalificador (50 años o más) en cuanto
exista el dato.

#### Scenario: Edad declarada
- **WHEN** el candidato responde "tengo 45" tras la pregunta de edad
- **THEN** se persiste `candidate.age=45` y el funnel continúa

#### Scenario: Edad descalificante también se persiste
- **WHEN** el candidato responde "tengo 52" tras la pregunta de edad
- **THEN** se persiste `candidate.age=52` y el planner dispara el descarte

### Requirement: Residencia en Laredo es ambigua y requiere desambiguación

El sistema SHALL tratar como ambiguo el valor "Laredo" declarado como residencia y SHALL NOT fijarlo como `candidate.city` firme sin desambiguar entre **Nuevo Laredo, Tamaulipas** (México) y **Laredo, Texas** (EUA). El sistema SHALL emitir una pregunta de desambiguación. Aplica cuando hay marcador de residencia en primera persona ("soy de", "vivo en", "radico en", "estoy en"). NO aplica cuando "Laredo" aparece dentro de una pregunta de ruta (p. ej. "¿qué rutas tienen para Nuevo Laredo?"), que no es declaración de residencia y ya no persiste ciudad por el guard de geo existente.

#### Scenario: "Soy de Laredo" → desambiguar, no fijar ciudad firme
- **WHEN** el candidato declara residencia en "Laredo" sin especificar Tamaulipas o Texas
- **THEN** el sistema no fija `candidate.city` como valor firme/confirmado
- **AND** el sistema pregunta si se refiere a Nuevo Laredo, Tamaulipas, o Laredo, Texas

#### Scenario: "Nuevo Laredo" explícito → ciudad mexicana sin ambigüedad
- **WHEN** el candidato declara residencia en "Nuevo Laredo" o "Laredo, Tamaulipas"
- **THEN** el sistema fija la ciudad mexicana sin pedir desambiguación

#### Scenario: Laredo dentro de pregunta de ruta no dispara desambiguación
- **WHEN** el candidato pregunta por rutas hacia Nuevo Laredo sin marcador de residencia
- **THEN** no se persiste `candidate.city` y no se emite pregunta de desambiguación

### Requirement: Residencia en Laredo, Texas se canaliza como ruta de EUA

El sistema SHALL marcar `requires_human` y canalizar a un reclutador humano cuando la desambiguación resuelve a **Laredo, Texas** (EUA), o el candidato menciona Laredo Texas / lado americano / cruce, aplicando el mismo tratamiento que una vacante de EUA, sin perfilar como vacante estándar.

#### Scenario: Laredo Texas → handoff
- **WHEN** la residencia se resuelve a Laredo, Texas (lado americano)
- **THEN** el contrato vivo resuelve `requires_human=true`
- **AND** el sistema canaliza a un reclutador humano sin emitir juicio de elegibilidad

### Requirement: Geo no se extrae de preguntas sin marcador de residencia

El sistema NO SHALL persistir `candidate.city` ni `candidate.state` desde un
mensaje que es una pregunta, salvo que contenga un marcador de residencia en
primera persona ("soy de", "vivo en", "radico en", "resido en", "estoy en").
Aplica a ambos extractores del camino vivo (alias GeoArea de Neo4j y regex de
`profile_extractor`).

#### Scenario: Pregunta de rutas no fija ciudad
- **WHEN** el candidato pregunta "¿qué rutas maneja para nuevo laredo?"
- **THEN** no se persiste `candidate.city` y no se emiten labels `foraneo`/`validar_traslado`

#### Scenario: Pregunta con marcador de residencia sí fija ciudad
- **WHEN** el candidato escribe "soy de laredo, ¿a dónde salen las corridas?"
- **THEN** se persiste `candidate.city` con el valor acotado ("Laredo")

### Requirement: Captura de ciudad acotada

La extracción de ciudad por regex SHALL acotar la captura: corta en conectores e
interrogativos (y, con, a, ahí, donde, que, para, pero, como, cuando, tengo,
licencia, apto, cartas) y limita el valor a un máximo de 4 tokens.

#### Scenario: Ciudad seguida de pregunta no se traga la frase
- **WHEN** el candidato escribe "soy de Laredo ahí de donde a donde me toca ir?"
- **THEN** `candidate.city` capturada es "Laredo", no la frase completa

#### Scenario: Ciudades multi-palabra siguen funcionando
- **WHEN** el candidato escribe "vivo en san luis potosi"
- **THEN** `candidate.city` capturada es "San Luis Potosí" (o el alias canónico del catálogo)

### Requirement: Documento laboral persistido según residencia

El sistema SHALL persistir el documento laboral en el fact canónico de evidencia
(`documents.proof`) con su tipo: `cartas` o `semanas_imss`. La validez del documento SHALL
evaluarse según residencia (local de la ZM Laguna acepta cualquiera de los dos; foráneo requiere
cartas membretadas), pero el fact persistido SHALL reflejar lo que el candidato declaró, con
evidencia literal y sin sobrescribir un documento ya confirmado.

#### Scenario: Semanas IMSS declaradas
- **WHEN** el candidato dice que cuenta con su documento de semanas cotizadas del IMSS
- **THEN** el sistema persiste `documents.proof = semanas_imss`

#### Scenario: Cartas declaradas
- **WHEN** el candidato dice que cuenta con cartas laborales
- **THEN** el sistema persiste `documents.proof = cartas`

### Requirement: Estado vencido-en-trámite con comprobante

El sistema SHALL persistir una señal canónica de trámite con comprobante para licencia y/o apto
(p. ej. `license.tramite_comprobante = true`, `medical.tramite_comprobante = true`) cuando el
candidato declare que el documento está vencido pero tiene cita/trámite comprobable. Esta señal
es la fuente determinista para continuar con `aclaracion_pendiente` en vez de bloquear.

#### Scenario: Licencia vencida con comprobante
- **WHEN** el candidato dice que su licencia está vencida pero tiene comprobante de cita
- **THEN** el sistema persiste la señal de trámite con comprobante para la licencia

#### Scenario: Vencido sin comprobante no marca trámite
- **WHEN** el candidato dice que su licencia está vencida y no la está tramitando
- **THEN** el sistema no persiste señal de trámite con comprobante

### Requirement: Afirmación global no confirma vigencia

El sistema SHALL NOT persistir vigencia de licencia ni de apto a partir de afirmaciones globales
no específicas ("todo en regla", "todo bien", "todo en orden"); estas SHALL dejar la vigencia
como no confirmada (ambigua) para que el funnel pregunte el vencimiento.

#### Scenario: "Todo en regla" no escribe vigencia
- **WHEN** el candidato dice "tengo todo en regla"
- **THEN** el sistema no marca `license` ni `medical.apto_status` como vigentes

