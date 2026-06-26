## ADDED Requirements

### Requirement: Residencia local descrita sin lista cerrada de municipios

El corpus de respuesta SHALL describir la residencia "local de la ZM Laguna" sin enumerar una lista cerrada de municipios que pueda interpretarse como exhaustiva. Cuando el texto mencione municipios, MUST presentarlos como ejemplos no exhaustivos y remitir la determinación de localidad al catálogo `zm-laguna-locality-catalog` (que incluye `comarca_ampliada`: Francisco I. Madero, Chávez, etc.). El corpus MUST NOT inducir al modelo a clasificar como foránea una localidad que el catálogo considera local.

#### Scenario: Candidato de la comarca ampliada
- **WHEN** el RAG recupera el texto de documento laboral según residencia para un candidato de Francisco I. Madero (presente en `comarca_ampliada` del catálogo)
- **THEN** el texto recuperado no afirma ni implica que esa localidad sea foránea
- **AND** la respuesta es consistente con la señal determinista `location.is_local_laguna`

#### Scenario: Mención de municipios como ejemplo
- **WHEN** el corpus menciona municipios de la ZM Laguna
- **THEN** lo hace como ejemplos ("como Torreón, Gómez Palacio, Lerdo…") y no como enumeración cerrada que excluya el resto del catálogo

### Requirement: Voz de equipo en el corpus de respuesta

El corpus de respuesta autorizada SHALL referirse al área de reclutamiento como "nuestro equipo" y MUST NOT nombrar "Capital Humano" como un tercero ajeno, dado que el RAG emite estos textos de forma literal al candidato.

#### Scenario: Respuesta de pagaré/contractual
- **WHEN** el RAG recupera el texto sobre documentación contractual o pagaré
- **THEN** el texto dice "nuestro equipo se la explica" (o equivalente) y no "Capital Humano se la explica"

#### Scenario: Respuesta de reingreso
- **WHEN** el RAG recupera el texto sobre casos de reingreso
- **THEN** el texto refiere la revisión a "nuestro equipo" y no a "Capital Humano" como tercero

### Requirement: Respuesta no afirma requisitos ausentes del corpus

La respuesta de cara al candidato SHALL afirmar únicamente requisitos presentes en el corpus autorizado. El sistema MUST NOT inventar umbrales numéricos ni condiciones de descarte que el corpus no documente — en particular, MUST NOT afirmar un mínimo de años de experiencia, porque el corpus solo pregunta los años de experiencia sin fijar un mínimo.

#### Scenario: Pregunta por requisitos generales
- **WHEN** el candidato pregunta "¿qué requisitos piden?" y el RAG compone la respuesta
- **THEN** la respuesta no afirma "al menos N años de experiencia" ni ningún umbral que no esté en el corpus
- **AND** describe la experiencia como un dato a conocer, no como un mínimo de corte

### Requirement: Documentos de expediente enmarcados como posteriores a la precalificación

La respuesta de requisitos en precalificación SHALL presentar los documentos de expediente (RFC, CURP, INE, NSS, comprobante de domicilio, comprobante de estudios) como solicitados "más adelante, si el proceso avanza", según la política del corpus. El sistema MUST NOT listarlos como requisitos inmediatos para un candidato que apenas inicia.

#### Scenario: Candidato nuevo pregunta requisitos
- **WHEN** un candidato sin perfil pregunta los requisitos y la respuesta menciona RFC/CURP/INE/NSS
- **THEN** los enmarca como "más adelante le pediremos…" (si su proceso avanza)
- **AND** no los presenta como condición inmediata de la precalificación

### Requirement: Registro de trato consistente en el corpus

El corpus de respuesta SHALL usar un registro de trato consistente en **usted** (el registro del saludo oficial y la persona de Mundo). El corpus MUST NOT mezclar tú y usted dentro del contenido respondible, porque esa mezcla se propaga al texto que el LLM genera.

#### Scenario: Texto del corpus revisado
- **WHEN** se inspecciona cualquier respuesta pública autorizada del corpus
- **THEN** usa "usted/su/tiene/cuente" de forma consistente y no formas de "tú" (puedes, tengas, te indicar)

