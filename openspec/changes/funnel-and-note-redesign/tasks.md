> Convención: RED-first (test que falla → implementación → GREEN). Tests Groq-free en `api-test`.
> Implementación RAMA POR RAMA; cada rama se verifica 1×1 en producción (chat real) ANTES de
> marcar su task como completa. No marcar nada resuelto sin corroboración del usuario en Chatwoot/Telegram.

## 1. Extracción: ambigüedad, documento por residencia, vencido-en-trámite

- [x] 1.1 RED+impl: "todo en regla / todo bien" NO confirma vigencia de licencia ni apto — `current_turn`/`profile_extractor`
- [x] 1.2 RED+impl: `documents.proof` ∈ {cartas, semanas_imss} como fact canónico; consolidar lectura desde `documents.labor_letters*`
- [x] 1.3 RED+impl: señal `license.tramite_comprobante` / `medical.tramite_comprobante` (vencido + comprobante de cita)

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

## 5. Pre-handoff condicional (hallazgos prod 2026-06-23)

> Antes de canalizar a Capital Humano, el bot verifica el dato mínimo que determina
> si el candidato es viable en su categoría. Solo entonces envía el acuse de handoff.

- [ ] 5a.1 RED+impl rama **escuelita pre-handoff**: preguntar si tiene licencia B/E vigente o comprobante de cita; si sí → canalizar con esa info; si no → indicar que debe tener licencia vigente para ser considerado y no continuar funnel
- [ ] 5a.2 RED+impl rama **CECATI pre-handoff**: mismo flujo de licencia que 5a.1 (sin licencia vigente/trámite no aplica aún; con licencia → revisar escuelita disponible)
- [ ] 5a.3 RED+impl rama **B1 pre-handoff**: preguntar tipo de unidad (full/sencillo) y si tiene licencia y apto vigentes antes de canalizar; nota IA refleja lo recolectado
- [ ] 5a.4 RED+impl rama **reingreso pre-handoff**: preguntar tipo de vacante (operador u otra); si operador → verificar ciudad + licencia + apto; si otra vacante → canalizar directo sin funnel adicional; nota IA refleja motivo
- [ ] 5a.5 Verificar que `Siguiente acción` en nota IA para reingreso NO diga "continuar flujo" sino la acción concreta pendiente (verificar historial, confirmar vacante, etc.)

## 6. Verificación y cierre

- [ ] 6.1 Suite Groq-free en `api-test` verde (actualizar tests del formato técnico viejo, no ignorarlos)
- [ ] 6.2 Rebuild + recreate; verificación 1×1 en producción (chat real) por rama
- [ ] 6.3 `openspec validate funnel-and-note-redesign --strict` + `openspec validate --specs --strict`
- [ ] 6.4 Sincronizar deltas a specs principales y archivar el change
