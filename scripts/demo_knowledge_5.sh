#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="${ENDPOINT:-http://localhost:8000/orchestrate/message}"
CHANNEL="${CHANNEL:-}"
RUN_ID="${RUN_ID:-demo_$(date +%Y%m%d_%H%M%S)}"

cases=(
  "Pago|cuanto pagan por kilometro"
  "Documentos|que documentos piden"
  "Seguridad|hacen prueba de orina o antidoping"
  "Recuperacion|desde ayer estoy esperando y ya me hablaron de otro lado"
  "Seguridad en ruta|voy manejando"
)

printf 'Demo endpoint: %s\n' "$ENDPOINT"
if [ -n "$CHANNEL" ]; then
  printf 'Canal: %s\n' "$CHANNEL"
fi
printf 'Run ID: %s\n\n' "$RUN_ID"

for i in "${!cases[@]}"; do
  raw="${cases[$i]}"
  label="${raw%%|*}"
  message="${raw#*|}"
  case_num=$(printf '%02d' $((i + 1)))
  user_id="${RUN_ID}-${case_num}"

  printf '%s\n' '================================================================================'
  printf 'CASO %s - %s\n' "$case_num" "$label"
  printf 'Candidato: %s\n\n' "$message"

  if [ -n "$CHANNEL" ]; then
    payload=$(jq -cn \
      --arg channel "$CHANNEL" \
      --arg user_id "$user_id" \
      --arg message "$message" \
      '{channel:$channel, channel_user_id:$user_id, message:$message}')
  else
    payload=$(jq -cn \
      --arg user_id "$user_id" \
      --arg message "$message" \
      '{channel_user_id:$user_id, message:$message}')
  fi

  response=$(curl -s "$ENDPOINT" \
    -H "Content-Type: application/json" \
    -d "$payload")

  echo "$response" | jq -r '
    "Ruta: \(.selected_route) | Intent: \(.intent) | Riesgo: \(.risk_level)" +
    "\nRAG: \(.requires_rag) | Humano: \(.requires_human) | Clarificacion: \(.requires_clarification)" +
    "\nLatencia servidor: \(.timings.total_ms // 0) ms | Recuperacion: \(.timings.retrieve_context_ms // 0) ms | Generacion: \(.timings.generate_answer_ms // 0) ms" +
    "\nCosto estimado: $\(.cost.total_usd_est // 0) USD" +
    "\n\nRespuesta:\n\(.reply)"
  '

  sleep 0.3
done

printf '\n%s\n' '================================================================================'
printf 'Demo terminada.\n'
