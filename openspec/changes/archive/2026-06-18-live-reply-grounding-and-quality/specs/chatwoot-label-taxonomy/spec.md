## ADDED Requirements

### Requirement: Labels de perfil listo y seguimiento por llamada

El sistema SHALL, cuando el perfil esté completo (`perfil_listo`) y el candidato pida una
llamada dentro del horario de oficina (8:00–17:30, `America/Mexico_City`, lunes a viernes),
poder derivar `perfil_listo` junto con `llamada_pendiente` y, cuando aplique,
`seguimiento`/`urgente`. Fuera del horario, el sistema SHALL registrar la solicitud y
mantener `llamada_pendiente` si requiere contacto humano, aclarando que el equipo contacta
en horario de atención. `llamada_pendiente` SHALL emitirse solo desde una decisión
determinista basada en Postgres/lead_memory; el LLM no decide labels.

> Nota de implementación: doc-only. `perfil_listo`, `seguimiento`, `urgente` y
> `llamada_pendiente` ya están en el catálogo oficial. Falta implementar el flujo
> `call_scheduling`: guardar `scheduling.call_requested`, `scheduling.call_status`,
> `scheduling.call_window_text` y `scheduling.call_window_valid`, y reflejar la ventana
> solicitada en la nota privada. El sistema SHALL NOT prometer una agenda real mientras no
> exista sistema de agendación.

#### Scenario: Perfil listo pide llamada en horario
- **WHEN** `perfil_listo` y el candidato pide llamada dentro de 8:00–17:30 (`America/Mexico_City`, lunes a viernes)
- **THEN** el sistema puede derivar `perfil_listo` + `llamada_pendiente` (y `seguimiento`/`urgente` si aplica)
- **AND** registra la ventana solicitada por el candidato cuando exista evidencia textual

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
