# Spec: city-extraction (delta)

## MODIFIED Requirements

### R-city-1 — Prioridad de fuente cuando hay marcador de residencia

**Antes**: el flujo era catálogo primero → LLM fallback. El catálogo podía capturar ciudades de destino ("pa ir a torreon") antes de anclar al marcador de residencia.

**Después**: cuando el mensaje contiene un marcador de residencia (`"soy de"`, `"soy d "`, `"soi de"`, `"vivo en"`, `"radico en"`, `"resido en"`, `"estoy en"`), el LLM T=0 es la fuente primaria para `candidate.city`.

- **LLM primero**: recibe el mensaje original, ancla la extracción al marcador, maneja typos de ciudad
- **Catálogo fallback**: solo si el LLM falla con excepción — busca en zona post-marcador
- **Sin marcador**: el catálogo es suficiente (respuesta directa como "torreon", "hermosillo")

### R-city-2 — Marcadores reconocidos

Lista exhaustiva (check en `text` normalizado Y en `message.lower()` para manejar variantes sin typo-canon):
- `"soy de"`, `"soy d "` (abreviado)
- `"soi de"`, `"soi d "` (variante ortográfica)
- `"vivo en"`, `"vivo n "` (abreviado)
- `"radico en"`, `"resido en"`, `"estoy en"`

Esta misma lista debe estar sincronizada en:
- `app/lead_memory/profile_extractor.py` → `_residence_markers`
- `app/orchestrators/knowledge_orchestrator.py` → `_RESIDENCE_MARKERS` (para `_drop_unanchored_neo4j_geo`)

### R-city-3 — Instrucción LLM: residencia vs destino

El prompt `_CITY_FALLBACK_SYSTEM` debe instruir explícitamente: cuando haya múltiples ciudades en el mensaje, extraer SOLO la ciudad inmediatamente después del marcador de residencia (no ciudades mencionadas como destino o ruta).

## Archivos afectados

- `app/lead_memory/profile_extractor.py` — `_extract_city()`, `_CITY_FALLBACK_SYSTEM`
- `app/orchestrators/knowledge_orchestrator.py` — `_RESIDENCE_MARKERS`
