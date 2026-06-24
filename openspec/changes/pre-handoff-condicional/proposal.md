## Why

Hoy cuando un candidato activa una rama de handoff (escuelita, CECATI, B1, reingreso), el bot lo canaliza de inmediato a Capital Humano sin verificar si tiene el dato mínimo que determina si es viable en esa categoría. Esto genera handoffs incompletos: el reclutador recibe leads sin saber si tienen licencia, qué tipo de vacante buscan, o si aplican al perfil base, obligando a llamadas de retorno que se podían evitar.

## What Changes

- **Escuelita pre-handoff**: antes de canalizar, preguntar si tiene licencia B/E vigente o comprobante de cita. Sin licencia → cerrar indicando que la licencia vigente es requisito previo.
- **CECATI pre-handoff**: mismo flujo de licencia que escuelita. Con licencia → canalizar con esa info.
- **B1/US pre-handoff**: preguntar tipo de unidad (full/sencillo) y confirmar que tiene licencia y apto vigentes antes de canalizar.
- **Reingreso pre-handoff**: preguntar tipo de vacante (operador u otra). Si operador → verificar ciudad + licencia + apto. Si otra vacante → canalizar directo sin funnel adicional.
- **Nota IA**: reflejar en `Siguiente acción` la acción concreta del handoff (verificar historial, confirmar vacante), no "continuar flujo automático".

## Capabilities

### New Capabilities

- `pre-handoff-verification`: Verifica el dato mínimo de viabilidad antes de canalizar a Capital Humano según la rama de handoff activada (escuelita, cecati, b1, reingreso). Determina si el candidato está listo para ser recibido por el reclutador o necesita completar un requisito previo.

### Modified Capabilities

- `handoff-routing`: El handoff ya no ocurre inmediatamente al detectar la señal; ahora pasa por una verificación previa cuyo resultado determina el acuse de handoff o el cierre informativo.
- `candidate-note`: `Siguiente acción` en la nota privada de Chatwoot debe reflejar la acción concreta pendiente según la rama, no un texto genérico.

## Impact

- `app/orchestrators/knowledge_orchestrator.py` — funciones `_apply_business_rule_overrides` y handoff branches (escuelita, cecati, b1, reingreso): añadir verificación previa antes de devolver `requires_human=True`.
- `app/knowledge/current_turn.py` — posible extensión de `next_question_from_missing_facts` o función nueva `next_prehandoff_question(branch, facts)` para las preguntas de verificación.
- `app/chatwoot_note_sync.py` — `render_candidate_note`: campo `Siguiente acción` condicionado al branch y datos recolectados.
- Tests en `tests/` — contratos Groq-free para cada rama (escuelita, cecati, b1, reingreso) verificando que el handoff solo ocurre cuando el dato mínimo está presente.
