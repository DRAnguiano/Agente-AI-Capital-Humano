> Convención: RED-first (test que falla → implementación → GREEN). Tests Groq-free en `api-test`.
> Implementación RAMA POR RAMA; cada rama se verifica 1×1 en producción (chat real) ANTES de
> marcar su task como completa. No marcar nada resuelto sin corroboración del usuario en Chatwoot/Telegram.

## 1. Extracción: ambigüedad, documento por residencia, vencido-en-trámite

- [ ] 1.1 RED+impl: "todo en regla / todo bien" NO confirma vigencia de licencia ni apto — `current_turn`/`profile_extractor`
- [ ] 1.2 RED+impl: `documents.proof` ∈ {cartas, semanas_imss} como fact canónico; consolidar lectura desde `documents.labor_letters*`
- [ ] 1.3 RED+impl: señal `license.tramite_comprobante` / `medical.tramite_comprobante` (vencido + comprobante de cita)

## 2. Funnel como ciclo (no estricto, solo ambiguo/no respondido)

- [ ] 2.1 RED: mensaje "soy Juan, 35, full 10 años, todo en regla" → solo pregunta licencia + ciudad + vigencia (no re-pregunta lo dado)
- [ ] 2.2 Implementar `next_funnel_question` como ciclo sobre la request completa (primer campo no resuelto NI ambiguo) — `intent_orchestrator.py`
- [ ] 2.3 RED+impl: no re-saludar ni re-preguntar dato ya confirmado en turnos previos
- [ ] 2.4 RED+impl: inferencia licencia→unidad (B→sencillo; E→full/sencillo; B pidiendo full → aclarar)
- [ ] 2.5 RED+impl: documento laboral por residencia (local: cartas o IMSS; foráneo: 2 cartas membretadas); solo documento laboral en esta etapa

## 3. Bienvenida y cierre por vigencia

- [ ] 3.1 RED+impl: primera interacción = bienvenida + (resolver duda) + anunciar serie de preguntas (sin pedir documentación) + pedir nombre; solo la primera vez
- [ ] 3.2 RED+impl: tras resolver duda, puente "si le interesa la vacante, ¿podría…?" (reusar requisito existente de puente suave)
- [ ] 3.3 RED+impl: vencido sin trámite → mensaje de retomar + `requiere_agente` + bot deja de responder + nota lo refleja; vencido con comprobante → `aclaracion_pendiente` continúa

## 4. Nota administrativa por escenario (render_candidate_note)

- [ ] 4.1 RED+impl: formato administrativo base (Estado del candidato / Lo que ya sabemos / Falta confirmar / Para Capital Humano / Siguiente acción); sin Canal/Embudo/Etapa/Bloqueo/Requiere humano; Riesgo solo si riesgo_alto; Requiere Agente
- [ ] 4.2 RED+impl rama **escuelita**: cabecera + experiencia no objetivo + licencia B/E mínima; no lista apto/cartas/ciudad
- [ ] 4.3 RED+impl rama **perfil listo local**: ciudad exacta ZM + documento "cartas o IMSS"
- [ ] 4.4 RED+impl rama **perfil listo foráneo**: documento "2 cartas membretadas" + traslado
- [ ] 4.5 RED+impl rama **vencido-en-trámite** y **pendiente por licencia/apto**
- [ ] 4.6 RED+impl ramas **CECATI / B1 / reingreso / no-aplica / edad fuera / riesgo / unidad ambigua**
- [ ] 4.7 RED+impl: `Siguiente acción` dinámica (avanza al siguiente pendiente; núcleo local/foráneo completo → cierre correspondiente)

## 5. Verificación y cierre

- [ ] 5.1 Suite Groq-free en `api-test` verde (actualizar tests del formato técnico viejo, no ignorarlos)
- [ ] 5.2 Rebuild + recreate; verificación 1×1 en producción (chat real) por rama
- [ ] 5.3 `openspec validate funnel-and-note-redesign --strict` + `openspec validate --specs --strict`
- [ ] 5.4 Sincronizar deltas a specs principales y archivar el change
