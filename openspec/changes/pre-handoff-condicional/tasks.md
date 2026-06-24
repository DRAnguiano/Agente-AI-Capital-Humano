> Convención: RED-first (test que falla → implementación → GREEN). Tests Groq-free donde sea posible.
> Verificación 1×1 en producción (chat real) ANTES de marcar completa.

## 1. Función de verificación previa

- [ ] 1.1 RED+impl: `next_prehandoff_question(branch, facts) -> str | None` en `current_turn.py` — retorna la pregunta de verificación pendiente para el branch dado, o `None` si el dato mínimo ya está en facts
- [ ] 1.2 Contratos de `next_prehandoff_question`: escuelita (sin licencia → pregunta), B1 (sin unidad → pregunta), reingreso (sin tipo_vacante → pregunta), dato completo → None

## 2. Rama escuelita/CECATI pre-handoff

- [ ] 2.1 RED: test — señal escuelita + sin licencia → bot pregunta "¿Tiene licencia federal?" en vez de hacer handoff
- [ ] 2.2 impl: en `_apply_business_rule_overrides`, antes de `requires_human=True` en rama escuelita/cecati, consultar `lead_memory.facts` para `license.category`; si ausente → devolver respuesta-pregunta (no handoff)
- [ ] 2.3 RED+impl: señal escuelita + licencia B/E confirmada → handoff con acuse que menciona tipo de licencia
- [ ] 2.4 RED+impl: candidato confirma no tener licencia → cierre informativo, sin handoff

## 3. Rama B1 pre-handoff

- [ ] 3.1 RED: test — señal B1 + sin `experience.vehicle_type` → bot pregunta tipo de unidad antes de canalizar
- [ ] 3.2 impl: en rama B1 de `_apply_business_rule_overrides`, verificar vehicle_type + license + apto; si falta alguno → preguntar primer campo faltante
- [ ] 3.3 RED+impl: B1 con todos los datos → handoff con acuse que menciona unidad

## 4. Rama reingreso pre-handoff

- [ ] 4.1 RED: test — señal reingreso + sin `reingreso.tipo_vacante` → bot pregunta "¿Operador u otro tipo de vacante?"
- [ ] 4.2 impl: en rama reingreso de `_apply_business_rule_overrides`, si `reingreso.tipo_vacante` no está en facts → preguntar
- [ ] 4.3 RED+impl: reingreso confirma operador + tiene datos completos → handoff con acuse específico
- [ ] 4.4 RED+impl: reingreso confirma otro tipo de vacante → handoff directo sin funnel adicional

## 5. Nota IA — Siguiente acción por rama

- [ ] 5.1 RED+impl: `render_candidate_note` — `Siguiente acción` para reingreso dice acción concreta (verificar historial) no texto genérico
- [ ] 5.2 RED+impl: `Siguiente acción` para escuelita/CECATI con licencia confirmada → "Confirmar disponibilidad de generación"
- [ ] 5.3 RED+impl: `Siguiente acción` para B1 con datos → "Revisar vacante B1/US para operador de [unidad]"

## 6. Verificación y cierre

- [ ] 6.1 Suite Groq-free verde para todas las ramas
- [ ] 6.2 Rebuild + recreate; verificación 1×1 en producción por rama
- [ ] 6.3 `openspec validate pre-handoff-condicional --strict`
- [ ] 6.4 Sincronizar deltas a specs principales y archivar el change
