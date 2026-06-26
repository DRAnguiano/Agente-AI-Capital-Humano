## Context

La conversación 121 (David, residente de Francisco I. Madero) corrió sobre el código posterior al fix `geo-truth-and-hardcoded-fallback-audit` y aún expuso cuatro inconsistencias. Dos son de **contrato de valor de fact** (un productor escribe un valor/tipo que el consumidor no reconoce) y dos son de **data de respuesta** (el corpus RAG contradice el catálogo y la voz de equipo).

Estado actual confirmado (archivo:línea):
- `app/knowledge/turn_extractor.py:110` define el contrato `documents.proof ∈ {cartas|semanas_imss|ninguno}`.
- `app/knowledge/current_turn.py:186` (`_has_labor_document`) solo reconoce `{"cartas","semanas_imss","sí","si"}`.
- `app/lead_memory/profile_extractor.py:457-467` ya escribe valores canónicos; el path que filtró `"cartas laborales"` crudo es la materialización de `answers_to_persist` del LLM (intent_classifier), que no pasa por un normalizador.
- `app/knowledge/current_turn.py:381` y `app/tasks_chatwoot.py:422` asignan `is_zm_laguna_canonical(...)` (retorna `bool`) directo al fact `location.is_local_laguna`; los consumidores (`current_turn.py:44`, `intent_orchestrator.py:33`) comparan `== "true"` (string).
- `data/02_documentos_requisitos.md:20,70` enumera 4 municipios locales; `:129,137` dicen "Capital Humano". `data/zm_laguna_localities.json` tiene `zm_laguna` + `comarca_ampliada` (Madero, Chávez).

## Goals / Non-Goals

**Goals:**
- Un solo punto de normalización para `documents.proof` que toda ruta de escritura atraviese.
- Representación única string `"true"`/`"false"` para `location.is_local_laguna` en todos los puntos de escritura.
- Corpus de respuesta consistente con el catálogo (sin lista cerrada) y con voz de equipo.
- Reproducir conv 121 con un solo cierre del paso documental y sin "foráneo"/"Capital Humano".

**Non-Goals:**
- No se cambia el catálogo `zm_laguna_localities.json` ni `geo_utils` (son la fuente de verdad correcta).
- No se reescribe el extractor determinista (ya emite canónico).
- No se introduce migración de datos históricos: el fix aplica a escrituras nuevas.
- No se toca el flujo de routing ni el prompt RAG (ya cubiertos por el change previo).

## Decisions

**D1 — Normalizar `documents.proof` en un helper compartido, invocado en el punto de escritura del path LLM.**
Se añade (o reutiliza) una función `canonicalize_proof(value) -> "cartas"|"semanas_imss"|"ninguno"|None` y se invoca donde `answers_to_persist`/`intent_classifier` materializa el fact, antes de `upsert`. *Alternativa descartada:* ampliar `_has_labor_document` para aceptar texto libre — propaga el problema a cada consumidor y no impone un contrato; rechazada.

**D2 — Emitir string en el punto de asignación, no en el de lectura.**
`location.is_local_laguna` se asigna como `"true" if is_zm_laguna_canonical(city) else "false"` en los dos puntos de escritura. *Alternativa descartada:* normalizar en cada consumidor (aceptar bool y string) — multiplica los sitios a tocar y deja la representación ambigua en la persistencia; rechazada por la regla de fuente única.

**D3 — Redactar el corpus con ejemplos no exhaustivos y delegar la determinación al catálogo.**
En `02_documentos_requisitos.md` se cambia "(Torreón, Gómez Palacio, Lerdo, Matamoros)" por una redacción con "como Torreón, Gómez Palacio, Lerdo, entre otras localidades de la Comarca Lagunera". El RAG deja de tener una lista cerrada que contradiga el catálogo. *Alternativa descartada:* copiar el catálogo completo al corpus — lo vuelve a duplicar y se desincroniza; rechazada.

**D4 — Voz de equipo directa en el corpus.**
Reemplazo textual de "Capital Humano" → "nuestro equipo" en las dos líneas autorizadas. Tras editar la data se reindexa el corpus RAG.

## Risks / Trade-offs

- **[El normalizador de `proof` no cubre alguna variante regional]** → mapear a `None` (no persistir) en vez de guardar crudo: el paso sigue abierto pero sin valor inválido; se observa en logs y se amplía el mapeo.
- **[Reindexado del RAG no corre tras editar la data]** → incluir el paso de reindex en tasks y verificar que la respuesta recuperada ya no enumera 4 municipios ni dice "Capital Humano".
- **[Datos históricos con `is_local_laguna` bool o `proof` crudo persistidos]** → no se migran; el riesgo es residual porque la señal se recomputa por turno y el helper de residencia ya cae al catálogo por ciudad.
- **[Otros archivos del corpus repiten la lista de 4 municipios]** → grep de confirmación sobre `data/` para no dejar copias.

## Migration Plan

1. Editar código (D1, D2) y data (D3, D4).
2. Reindexar corpus RAG.
3. `docker compose build worker api && docker compose up -d worker api` (código baked en imagen).
4. Verificar reproduciendo conv 121.
Rollback: revertir el commit; sin estado persistente nuevo que limpiar.

## Open Questions

- ¿El normalizador de `proof` debe vivir en `profile_extractor.py` (junto a los upserts canónicos existentes) o en un módulo de canonicalización compartido? Se decide en apply según dónde se materializa `answers_to_persist`.
