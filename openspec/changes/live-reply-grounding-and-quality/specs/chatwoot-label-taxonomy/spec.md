## ADDED Requirements

### Requirement: Labels de perfil listo y seguimiento por llamada

El sistema SHALL, cuando el perfil esté completo (`perfil_listo`) y el candidato pida una
llamada dentro del horario de oficina (8:00–17:30, `America/Monterrey`, lunes a viernes),
poder derivar `perfil_listo` junto con `seguimiento` y, cuando aplique, `urgente`. Fuera del
horario, el sistema SHALL derivar `perfil_listo` con `seguimiento`. El sistema SHALL NOT
emitir un label de llamada que aún no exista en el catálogo oficial: `llamada_pendiente`
SHALL añadirse primero al catálogo de `chatwoot-label-taxonomy` antes de poder emitirse.

> Nota de implementación: doc-only. `perfil_listo`, `seguimiento` y `urgente` ya están en el
> catálogo oficial; `llamada_pendiente` es FUTURO (`multi-intent-migration` / `call_scheduling`).
> El sistema SHALL NOT prometer una agenda real mientras no exista sistema de agendación.

#### Scenario: Perfil listo pide llamada en horario
- **WHEN** `perfil_listo` y el candidato pide llamada dentro de 8:00–17:30 (`America/Monterrey`, lunes a viernes)
- **THEN** el sistema puede derivar `perfil_listo` + `seguimiento` (y `urgente` si aplica)
- **AND** no emite `llamada_pendiente` mientras no esté en el catálogo oficial

#### Scenario: Perfil listo fuera de horario
- **WHEN** `perfil_listo` y el candidato pide llamada fuera del horario de oficina
- **THEN** el sistema deriva `perfil_listo` + `seguimiento`
- **AND** no afirma que la llamada ya quedó agendada

### Requirement: No emitir labels fuera del catálogo oficial

El sistema SHALL emitir únicamente labels presentes en el catálogo oficial de
`chatwoot-label-taxonomy` y SHALL NOT emitir labels fantasma. Los labels calculados, los
sincronizados a Chatwoot y el catálogo oficial SHALL estar alineados. El concepto de cartas
laborales/documentos SHALL usar el label oficial `documentos` (no `falta_cartas`, que no
existe en el catálogo).

> Nota de implementación: doc-only. Caso observado: `falta_cartas` apareció en una nota pero no
> está en el catálogo (`falta_apto`/`falta_ciudad`/`falta_experiencia`/`falta_licencia`/
> `falta_unidad` + `documentos`).

#### Scenario: Label fuera del catálogo no se emite
- **WHEN** un cálculo propone `falta_cartas` u otra label fuera del catálogo oficial
- **THEN** el sistema no la emite ni la sincroniza a Chatwoot
- **AND** usa el label oficial correspondiente (p. ej. `documentos`) cuando aplique
