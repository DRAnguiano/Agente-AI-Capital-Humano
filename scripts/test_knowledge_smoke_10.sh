#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="${ENDPOINT:-http://localhost:8000/orchestrate/message}"
CHANNEL="${CHANNEL:-test_knowledge_orchestrator}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
OUT_JSONL="${OUT_JSONL:-/tmp/hr_knowledge_smoke_10_${RUN_ID}.jsonl}"
SLEEP_SECONDS="${SLEEP_SECONDS:-0.2}"

cases=(
  "pago|rag|cuanto pagan por kilometro"
  "documentos|rag|que documentos piden"
  "antidoping|rag|hacen prueba de orina o antidoping"
  "rutas|rag|cuales son las rutas o bases"
  "escuelita|rag|tienen escuelita para quinta rueda"
  "dropoff|candidate_dropoff_recovery|desde ayer estoy esperando y ya me hablaron de otro lado"
  "cierre|candidate_dropoff_recovery|gracias ya consegui trabajo"
  "jerga|clarification|kchmbr"
  "ruta_segura|profile|voy manejando"
  "callback|profile|me pueden llamar"
)

printf 'Endpoint: %s\n' "$ENDPOINT"
printf 'Channel:  %s\n' "$CHANNEL"
printf 'Total casos: %s\n' "${#cases[@]}"
printf 'Output JSONL: %s\n\n' "$OUT_JSONL"
: > "$OUT_JSONL"

for i in "${!cases[@]}"; do
  raw="${cases[$i]}"
  group="${raw%%|*}"
  rest="${raw#*|}"
  expected="${rest%%|*}"
  message="${rest#*|}"
  case_num=$(printf '%02d' $((i + 1)))
  user_id="smoke-${RUN_ID}-${case_num}"

  printf '%s\n' '================================================================================'
  printf 'CASO %s | grupo=%s | expected=%s\n' "$case_num" "$group" "$expected"
  printf 'Mensaje: %s\n' "$message"

  payload=$(jq -cn \
    --arg channel "$CHANNEL" \
    --arg user_id "$user_id" \
    --arg message "$message" \
    '{channel:$channel, channel_user_id:$user_id, message:$message}')

  start_ms=$(python - <<'PY'
import time
print(int(time.time() * 1000))
PY
)

  response=$(curl -s "$ENDPOINT" \
    -H "Content-Type: application/json" \
    -d "$payload")

  end_ms=$(python - <<'PY'
import time
print(int(time.time() * 1000))
PY
)

  latency_ms=$((end_ms - start_ms))

  echo "$response" | jq -c \
    --arg group "$group" \
    --arg expected "$expected" \
    --arg message "$message" \
    --argjson latency_ms "$latency_ms" \
    '. + {test_group:$group, expected_route:$expected, test_message:$message, client_latency_ms:$latency_ms}' \
    >> "$OUT_JSONL"

  echo "$response" | jq \
    --arg expected "$expected" \
    --argjson latency_ms "$latency_ms" \
    '{
      expected_route: $expected,
      selected_route,
      pass: (.selected_route == $expected),
      intent,
      risk_level,
      requires_rag,
      requires_human,
      requires_clarification,
      client_latency_ms: $latency_ms,
      server_total_ms: .timings.total_ms,
      retrieve_context_ms: .timings.retrieve_context_ms,
      generate_answer_ms: .timings.generate_answer_ms,
      rag: .rag,
      cost: .cost,
      reply
    }'

  sleep "$SLEEP_SECONDS"
done

printf '\n%s\n' '================================================================================'
printf 'Resumen:\n'
jq -s '
  {
    total: length,
    passed: map(select(.selected_route == .expected_route)) | length,
    failed: map(select(.selected_route != .expected_route)) | length,
    avg_client_latency_ms: ((map(.client_latency_ms // 0) | add) / length | round),
    avg_server_total_ms: ((map(.timings.total_ms // 0) | add) / length | round),
    avg_retrieve_context_ms: ((map(.timings.retrieve_context_ms // 0) | add) / length | round),
    avg_generate_answer_ms: ((map(.timings.generate_answer_ms // 0) | add) / length | round),
    total_estimated_usd: (map(.cost.total_usd_est // 0) | add),
    routes: (group_by(.selected_route) | map({route: .[0].selected_route, total: length})),
    failures: map(select(.selected_route != .expected_route) | {message: .test_message, expected: .expected_route, got: .selected_route, intent})
  }
' "$OUT_JSONL"

printf '\nJSONL guardado en: %s\n' "$OUT_JSONL"
