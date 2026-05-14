# Agente RH Transmontes

Agente conversacional para reclutamiento de operadores de quinta rueda.

El sistema usa FastAPI, ChromaDB, embeddings locales y Groq como LLM remoto. n8n queda como orquestador para conectar Telegram, webhooks y otros canales.

## Componentes

- FastAPI: API principal.
- ChromaDB: base vectorial persistente.
- Sentence Transformers: embeddings para documentos locales.
- Groq: modelo conversacional remoto.
- n8n: automatizacion de canales.
- ngrok: exposicion publica de n8n.

## Flujo

```text
Telegram / webhook
        |
       n8n
        |
   POST /ask
        |
FastAPI + RAG
        |
Groq
        |
Respuesta al candidato
```

## Variables principales

Crear `.env` en la raiz:

```env
GROQ_API_KEY=tu_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_MAX_TOKENS=1024

EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
TOP_K=3
CHUNK_SIZE=800
CHUNK_OVERLAP=150
REINDEX_CLEAN=false

NGROK_AUTHTOKEN=tu_token
NGROK_DOMAIN=tu-dominio.ngrok-free.dev
TELEGRAM_BOT_TOKEN=tu_token
```

## Uso

Levantar servicios:

```bash
docker compose up -d --build
```

Verificar API:

```bash
curl http://localhost:8000/health
```

Indexar documentos en `data/`:

```bash
curl -X POST http://localhost:8000/reindex
```

Probar una conversacion:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"q":"Tengo 5 anos manejando quinta rueda y licencia federal vigente","top_k":3}'
```

## Documentos

Coloca en `data/` los PDFs o textos que el agente puede usar para responder dudas sobre requisitos, pagos, prestaciones, apto medico, valores y proceso interno.

El agente no debe inventar datos fuera de esos documentos.
