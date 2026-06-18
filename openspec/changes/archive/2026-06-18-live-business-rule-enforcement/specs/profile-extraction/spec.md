# profile-extraction (delta)

## ADDED Requirements

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
