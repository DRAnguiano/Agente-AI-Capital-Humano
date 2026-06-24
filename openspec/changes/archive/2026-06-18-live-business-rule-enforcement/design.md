# Design: live-business-rule-enforcement

## Contexto del camino vivo (hecho auditado)

```
webhook (app.py)  →  tasks_chatwoot.py  →  knowledge_orchestrator.handle_message
                                                │
                                                ├─ resolve_message()  [neo4j_client.py]
                                                │     match de aliases contra el seed Neo4j
                                                │     → contract {route, intent, risk_level}
                                                ├─ _apply_profile_guards / _apply_deterministic_overrides
                                                ├─ _route_flags() → requires_human =
                                                │     route ∈ {human_handoff, policy_boundary} or risk=high
                                                └─ run_shadow()  [fire-and-forget, NO muta estado]
```

- El `requires_human` vivo depende de que **el seed de Neo4j** tenga un término que
  matchee el mensaje con `route=human_handoff`. El seed NO tiene B1/US ni reingreso.
- Si Neo4j cae, `resolve_message` usa un **fallback genérico que no aplica reglas de
  dominio** — las reglas de seguridad se perderían justo en una caída.
- El `business-route-shadow-classifier` detecta B1/reingreso/escuelita, pero corre en
  `run_shadow()` y por contrato "no muta estado productivo".

## Decisión: política en código determinista, no en el seed

**El mecanismo es un guard determinista en Python**, no términos nuevos en el seed.

Razones:
1. **El seed es solo vocabulario.** Faltas ortográficas y coloquialismos ambiguos que
   ayudan al LLM a mapear lenguaje→concepto (licencia, apto, unidad). Una política
   operativa ("B1 → `requires_human`") no pertenece al vocabulario.
2. **Alineación con la migración.** `multi-intent-migration/design.md` (L22, L199-201,
   L237) separa la clasificación del lenguaje (LLM/grafo de conceptos) de las políticas
   de negocio (deterministas). Sembrar política en Neo empuja al grafo hacia donde la
   migración lo está sacando → deuda que el cutover tendría que volver a migrar.
3. **Testeabilidad y robustez.** Un guard Python se prueba con `api-test` sin Neo, y
   sigue aplicando aunque Neo esté caído (no depende del fallback).
4. **No duplicar detección.** La detección léxica de B1/US/reingreso/escuelita ya existe
   en `app/knowledge/business_route_*`; el guard la reusa en vez de copiarla al seed.

Lo que SÍ puede vivir en catálogo/grafo es la *detección del concepto* ("b1", "usa",
"cruce" como aliases). Lo que NO va al seed es la *decisión de política* ("→ handoff").

### Punto de inserción del guard (a definir en implementación)

Opción preferida: un guard determinista que corre **antes** de confiar en el contrato de
Neo, fijando `route=human_handoff` / `requires_human=true` cuando hay evidencia literal de
B1/US o reingreso. Coexiste con `_apply_deterministic_overrides` (greeting/farewell/hora),
que ya es el lugar de overrides deterministas en el orquestador vivo. La implementación
queda fuera de este change (solo contrato + tests RED).

## Alcance explícito

- **Incluye:** B1/US → handoff, reingreso → handoff, torton/rabón/reparto → escuelita,
  prohibición de emitir "caduca/caducidad", todo en el **camino vivo**.
- **Excluye:** OCR/audio (el media guard del webhook ya cubre multimedia → no inferir),
  Meta, RAG corpus, y cualquier cambio al shadow classifier.
- **No implementa lógica todavía:** entrega contrato + tests RED-first.
