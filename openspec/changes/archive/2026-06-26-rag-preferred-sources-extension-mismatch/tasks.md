## 1. Helper de normalización por stem

- [x] 1.1 Añadido `_source_stem(value)` en `context_builder.py`: lower + basename (quita prefijo de ruta) + quita extensión conocida (`.md/.markdown/.txt`); tolera `None`/vacío. Constante `_KNOWN_SOURCE_EXTS`.
- [x] 1.2 Verificado helper (ver tarea 3.x): `01_pago_prestaciones`, `01_pago_prestaciones.md`, `data/01_pago_prestaciones.md` → mismo stem.

## 2. Filtrado por stem en la recuperación

- [x] 2.1 `retrieve_preferred_context`: retirado el `where` estricto de Chroma; `query_n = max(requested_k*8, 24)` cuando hay `source_stems`, si no `requested_k`.
- [x] 2.2 Allowlist por stem: `source_stems = {_source_stem(s) ...}`; en el loop, item entra sólo si `_source_stem(source) in source_stems`. Sin filtro, ruta global intacta.
- [x] 2.3 `_dedupe_items(items)[:requested_k]` (existente) recorta tras filtrar por stem, preservando orden por score de Chroma.
- [x] 2.4 `_source_where` eliminado (sin referencias en código); comentario del seed cypher actualizado a "emparejamiento por stem". Sin lógica duplicada.

## 3. Verificación

- [x] 3.1 Reproducido en runtime: las 3 variantes (`[]`, `['01_pago_prestaciones.md']`, `['01_pago_prestaciones']`) devuelven **3 items** cada una (antes la sin-extensión daba 0).
- [x] 3.2 Aislamiento confirmado: con `['01_pago_prestaciones']` el único source es `01_pago_prestaciones.md`; ninguna otra fuente cuela.
- [x] 3.3 E2E `POST /orchestrate/message` (user `rag-verify-pago-001`): pregunta de pago responde con el rango $5,000–$10,000 del corpus, NO `NO_CONTEXT_REPLY`.
- [x] 3.4 Regresión `POST /orchestrate/message` (user `rag-verify-req-001`): requisitos sigue acotado a `02_documentos_requisitos` (licencia/apto/cartas), sin colar pago ni rutas.
- [x] 3.5 `docker compose build worker api && docker compose up -d worker api` ejecutado; api bind-mount, worker horneado.
- [x] 3.6 `openspec validate rag-preferred-sources-extension-mismatch --strict`.
