## 1. Temperatura cero en settings e indexer

- [x] 1.1 Cambiar `TEMPERATURE=0.10` a `TEMPERATURE=0.0` en `.env`
- [x] 1.2 Cambiar default en `app/settings.py`: `_env_float("TEMPERATURE", 0.1)` → `_env_float("TEMPERATURE", 0.0)`
- [x] 1.3 Cambiar fallback hardcodeado en `app/indexer.py` línea ~95: `os.getenv("TEMPERATURE", "0.15")` → `os.getenv("TEMPERATURE", "0.0")`

## 2. Auditoría de canned responses en orchestrator

- [x] 2.1 Revisar `app/orchestrators/knowledge_orchestrator.py` en busca de bancos regex→texto_fijo fuera de `_apply_business_rule_overrides` y `_NO_ANSWER_HINTS`; documentar hallazgos
- [x] 2.2 Eliminar cualquier banco canned identificado fuera de las políticas de negocio deterministas; si no hay, marcar como verificado

## 3. Verificar clasificador no afectado

- [x] 3.1 Confirmar que `call_groq_json` en `app/indexer.py` ya pasa `temperature=0.0` explícito (no heredar de `TEMPERATURE` global); si ya lo hace, solo marcar verificado

## 4. Deploy y validación

- [x] 4.1 Reiniciar `api` y `worker` con `docker compose restart api worker`
- [x] 4.2 Enviar mensaje de prueba de smalltalk y verificar en logs que Groq recibe `temperature: 0` y la respuesta no contiene datos inventados
- [x] 4.3 Enviar mensaje RAG (ej. "¿cuánto pagan por kilómetro?") y verificar respuesta acotada al contexto recuperado
