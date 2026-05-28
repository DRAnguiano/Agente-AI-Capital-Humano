# Demo readiness - Agente IA Capital Humano

Este documento deja el flujo de arranque, validacion y demo para presentar el agente sin depender de memoria ni de comandos sueltos.

## 1. Arquitectura activa

Flujo actual:

```text
/orchestrate/message
-> HR_GRAPH_MODE=knowledge
-> Knowledge Orchestrator
-> Neo4j Knowledge Graph
-> contrato limpio: intent, route, risk, preferred_sources
-> si route=rag: Chroma filtrado por preferred_sources
-> LLM principal para respuesta final
-> respuesta con timings, sources y costo estimado
```

LangGraph queda fuera del flujo principal. El objetivo de esta fase es mostrar una arquitectura mas limpia, trazable y barata de depurar.

## 2. Variables importantes de .env

```env
HR_GRAPH_MODE=knowledge
NEO4J_ENABLED=true
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_password
NEO4J_DATABASE=neo4j

LLM_PROVIDER=groq
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_MAX_TOKENS=350
TEMPERATURE=0.15

RAG_TOP_K=3
RAG_MIN_SCORE=0.25
RAG_MAX_CONTEXT_CHARS=2200
RAG_MAX_CHARS_PER_DOC=850
KNOWLEDGE_RAG_GENERATION_ENABLED=true
KNOWLEDGE_RAG_WARMUP_ON_STARTUP=true
KNOWLEDGE_RAG_WARMUP_TEXT=cuanto pagan por kilometro

WEB_SEARCH_ENABLED=false
UNKNOWN_TERM_WEB_SEARCH_ENABLED=true
UNKNOWN_TERM_WEB_USE_FOR_PUBLIC_ANSWER=false
```

No subir llaves reales al repositorio. Si hay duda, revisar `.env`, `.env.chatwoot` y logs antes de compartir capturas.

## 3. Arranque limpio

Desde la carpeta del proyecto:

```bash
cd "/mnt/d/DOCUMENTOS UBUNTU/Agente AI Capital Humano Transmontes"

git pull origin migration/langgraph-step1

docker compose -f docker-compose.yml -f docker-compose.neo4j.yml up -d
```

Si hubo cambios en Python o requirements:

```bash
docker compose -f docker-compose.yml -f docker-compose.neo4j.yml build --no-cache api worker
docker compose -f docker-compose.yml -f docker-compose.neo4j.yml up -d api worker
```

## 4. Verificar servicios

```bash
docker compose -f docker-compose.yml -f docker-compose.neo4j.yml ps
```

Servicios clave esperados:

```text
hr_rag_api
hr_worker
hr_postgres
hr_neo4j
chatwoot_rails
chatwoot_sidekiq
chatwoot_postgres
chatwoot_redis
ngrok
```

## 5. Cargar reglas en Neo4j

El seed es idempotente, se puede correr varias veces.

```bash
docker compose -f docker-compose.yml -f docker-compose.neo4j.yml exec -T neo4j cypher-shell \
  -u neo4j \
  -p neo4j_password \
  -f /var/lib/neo4j/import/neo4j_seed_hr_rules.cypher
```

Validacion rapida:

```bash
docker compose -f docker-compose.yml -f docker-compose.neo4j.yml exec -T neo4j cypher-shell \
  -u neo4j \
  -p neo4j_password \
  "MATCH (n) RETURN labels(n) AS labels, count(*) AS total ORDER BY total DESC;"
```

## 6. Verificar warmup RAG

```bash
docker compose -f docker-compose.yml -f docker-compose.neo4j.yml logs -f api
```

Buscar algo similar a:

```text
[indexer] Cargando embedding model: BAAI/bge-m3
[knowledge_rag_warmup] {'ok': True, 'collection_count': 57, 'elapsed_ms': ...}
```

Ese warmup evita que el primer candidato pague la carga del embedding model.

## 7. Smoke test de 10 casos

```bash
chmod +x scripts/test_knowledge_smoke_10.sh
./scripts/test_knowledge_smoke_10.sh
```

Resultado esperado:

```text
passed: 10
failed: 0
```

Este test valida rutas, intenciones, RAG, respuestas controladas, latencia y costo estimado.

## 8. Demo corta de 5 casos

```bash
chmod +x scripts/demo_knowledge_5.sh
./scripts/demo_knowledge_5.sh
```

Casos de demo:

```text
1. Pago
2. Documentos
3. Seguridad / antidoping
4. Recuperacion de candidato
5. Seguridad en ruta
```

Metricas esperadas:

```text
RAG: menor a 2 segundos en condiciones normales
Respuestas controladas sin RAG: menor a 200 ms
Costo por respuesta RAG: alrededor de 0.0004 USD
Casos sin LLM: 0 USD
```

## 9. Guion breve para presentar

Puntos a decir:

```text
Este agente no responde a ciegas. Primero consulta un grafo de conocimiento en Neo4j que define intencion, riesgo y fuente interna preferida.

Si el tema requiere documentos internos, usa RAG filtrado por esa fuente. Por ejemplo, preguntas de pago solo buscan en el documento de pago/prestaciones.

Si el caso no requiere LLM, como 'voy manejando' o 'ya me hablaron de otro lado', responde con plantillas controladas, mas rapido y sin costo de generacion.

Cada respuesta devuelve trazabilidad: ruta seleccionada, intencion, riesgo, fuentes usadas, latencia y costo estimado.

Esto permite usar IA de forma responsable: sin inventar condiciones, sin prometer contratacion y escalando casos sensibles cuando aplica.
```

## 10. Que mostrar en vivo

Recomendado:

1. Mostrar Neo4j con nodos Term, Intent, Route, ReplyTemplate, Policy e InternalSource.
2. Correr `./scripts/demo_knowledge_5.sh`.
3. Explicar una respuesta RAG: pago o documentos.
4. Explicar una respuesta sin LLM: voy manejando o recuperacion.
5. Mostrar costo y latencia por caso.

## 11. No hacer durante la demo

```text
No correr reindex si no es necesario.
No ejecutar pruebas masivas con Groq.
No mostrar .env con llaves.
No abrir logs con tokens visibles.
No depender de web search para respuestas publicas.
No prometer que el agente contrata o decide por RH.
```

## 12. Comandos de emergencia

Reiniciar API y worker:

```bash
docker compose -f docker-compose.yml -f docker-compose.neo4j.yml restart api worker
```

Ver logs API:

```bash
docker compose -f docker-compose.yml -f docker-compose.neo4j.yml logs -f api
```

Ver logs Neo4j:

```bash
docker compose -f docker-compose.yml -f docker-compose.neo4j.yml logs -f neo4j
```

Probar endpoint manual:

```bash
curl -s http://localhost:8000/orchestrate/message \
  -H "Content-Type: application/json" \
  -d '{"channel_user_id":"demo-manual-001","message":"cuanto pagan por kilometro"}' \
| jq '{selected_route, intent, risk_level, reply, rag, sources, cost, timings}'
```
