## ADDED Requirements

### Requirement: Vigencia enunciada se persiste aunque no se haya preguntado
El extractor SHALL persistir `license.expiration_text` y `medical.apto_expiration_text` cuando el candidato enuncia claramente la vigencia (un marcador de vencimiento inequívoco — "vence", "vigencia", "vencimiento", "caduca" — junto a un plazo o fecha válidos), aunque el último mensaje del bot no haya preguntado ese campo (`answered_direct_question` falso) y aunque el LLM no haya marcado `explicit_marker`. El valor SHALL seguir cumpliendo la validación de vigencia existente (las no-respuestas/evasivas siguen inválidas).

#### Scenario: Vigencia voluntariada antes de preguntarla
- **WHEN** el candidato dice "tengo licencia tipo E y vence en un año" mientras el bot había preguntado otra cosa (p. ej. el nombre)
- **THEN** se persiste `license.expiration_text` con el plazo y el funnel NO vuelve a preguntar la vigencia de la licencia

#### Scenario: Apto médico enunciado junto con otros datos
- **WHEN** el candidato dice "mi apto médico vence en 8 meses y tengo cartas laborales"
- **THEN** se persiste `medical.apto_expiration_text` con el plazo

#### Scenario: No-respuesta sigue inválida
- **WHEN** el candidato dice "no sé cuándo vence mi licencia"
- **THEN** NO se persiste una vigencia (la no-respuesta sigue inválida) y el funnel puede volver a pedirla

#### Scenario: Nombre suelto conserva su guarda
- **WHEN** el turno aporta un `candidate.name` sin marcador explícito ni pregunta directa
- **THEN** el comportamiento de `candidate.name` NO cambia con este requisito (sigue su guarda D3 original)
