# Tasks: live-business-rule-enforcement

> Regla de esta fase: contrato + tests primero. NO implementar lógica del guard hasta
> aprobación explícita. Los tests se escriben RED (fallan contra el camino vivo actual,
> que es justo la evidencia del gap auditado).

## Fase 0 — Auditoría (DONE, read-only)

- [x] 0.1 Confirmado: el `requires_human` vivo depende del seed Neo4j; el seed no tiene
  B1/US ni reingreso → no hay handoff vivo para esas reglas.
- [x] 0.2 Confirmado: torton/rabón/reparto ausentes del seed → sin señal escuelita viva.
- [x] 0.3 Confirmado: media guard ya es vivo en el webhook (`app.py`) → multimedia fuera
  de alcance de este change.
- [x] 0.4 Decisión de mecanismo: guard determinista en Python, no re-seed de Neo4j.

## Fase 1 — Tests RED contra el camino vivo (sin implementación)

> `tests/test_live_business_rules.py` creado. 17 casos en `xfail(strict=True)` contra las
> funciones planeadas de Fase 2 (guard determinista, léxico de vigencia, desambiguación
> Laredo). Verificado vía api-test: **17 xfailed, 0 fallos**. El gap queda reproducible y
> la suite verde; al implementar Fase 2 los tests harán XPASS y forzarán quitar el xfail.

- [x] 1.1 B1/US → `requires_human=true` vía `_apply_business_rule_overrides` (vacante B1,
  Estados Unidos, USA, cruce/visa, ruta americana) + caso con contrato de fallback Neo4j.
- [x] 1.2 Reingreso → `requires_human=true`; y "ya conseguí otro trabajo" NO es reingreso.
- [x] 1.3 Torton/rabón/reparto → señal escuelita y sin `vehicle_type` full/sencillo.
- [x] 1.4 Guard de salida `_enforce_vigencia_lexicon`: respuesta sin "caduca"/"caducidad".
- [x] 1.5 Laredo: `detect_laredo_ambiguity` True para "soy de Laredo"; False para "Nuevo
  Laredo" explícito y para Laredo dentro de pregunta de ruta.
- [x] 1.6 Laredo Texas → `requires_human=true`.

## Fase 2 — Implementación del guard (DONE)

- [x] 2.1 `_apply_business_rule_overrides` en `knowledge_orchestrator` (detección léxica
  determinista con límites de palabra sobre texto normalizado): B1/US y reingreso →
  `route=human_handoff`/`requires_human`; torton/rabón/reparto → señal escuelita reusando
  `domain_catalog.VEHICLE_TERMS` (NON_TARGET). Cableado tras `_apply_deterministic_overrides`,
  antes de `_route_flags`. NO toca el seed Neo4j; aplica aun en fallback de Neo4j.
- [x] 2.2 `_enforce_vigencia_lexicon` aplicado al `reply` final en `handle_message`
  (todas las rutas): "caducidad"→vigencia, "caducad[ao]s?"→vencid*, "caduca(n|r)?"→vence.
- [x] 2.3 `profile_extractor.detect_laredo_ambiguity` (residencia ambigua MX vs TX; no
  dispara en pregunta de ruta ni con "nuevo laredo"/"tamaulipas"/"texas" explícitos) +
  handoff de Laredo Texas vía `_B1_US_RE` ("laredo texas"/"laredo tx"/"lado americano").
- [x] 2.4 GREEN: `tests/test_live_business_rules.py` **17 passed**; suite general
  **598 passed, 0 fallos** (vía api-test). Sin regresiones.

## Fase 3 — Validación

- [x] 3.1 `openspec validate live-business-rule-enforcement --strict` → valid.
- [x] 3.2 Suite completa vía `api-test` (598 passed); `git diff --check` limpio.
- [ ] 3.3 Sin commit/push hasta autorización.

> Pendiente de consumo (fuera de este change): `detect_laredo_ambiguity` está disponible
> pero la EMISIÓN de la pregunta de desambiguación de Laredo en el flujo de respuesta
> (en vez de fijar ciudad) es un cableado adicional en el funnel; este change deja el
> detector + handoff de Texas. Evaluar en seguimiento si se conecta aquí o en funnel.
