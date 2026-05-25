#!/usr/bin/env sh
set -eu

BASE_URL="${BASE_URL:-http://localhost:8000}"
WARMUP_REINDEX="${WARMUP_REINDEX:-0}"

echo "[warmup] Waiting for API health..."
i=0
until curl -fsS "$BASE_URL/health" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "[warmup] API did not become healthy in time" >&2
    exit 1
  fi
  sleep 2
done

echo "[warmup] API healthy."

if [ "$WARMUP_REINDEX" = "1" ]; then
  echo "[warmup] Reindexing Chroma..."
  curl --max-time 600 -fsS -X POST "$BASE_URL/reindex" >/dev/null
  echo "[warmup] Reindex done."
fi

echo "[warmup] Warming LangGraph/RAG/LLM..."
curl --max-time 180 -fsS -X POST "$BASE_URL/orchestrate/message" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "system_warmup",
    "channel_user_id": "rag-warmup",
    "username": "Warmup",
    "phone": null,
    "message": "cuanto pagan por kilometro y que prestaciones dan?",
    "external_message_id": "warmup-demo-001"
  }' >/dev/null

echo "[warmup] Done."
