#!/usr/bin/env bash
# Demo helper — one short command per step (no pasting long curls).
cd "$(dirname "$0")"
BASE="${BASE_URL:-http://127.0.0.1:5000}"

submit() {
  local file="$1"
  local save_id="${2:-}"
  local out
  out=$(curl -s -X POST "$BASE/submit" -H "Content-Type: application/json" -d @"$file")
  echo "$out" | python3 -m json.tool
  if [[ -n "$save_id" ]]; then
    echo "$out" | python3 -c "import sys, json; print(json.load(sys.stdin)['content_id'])" > demo/.content_id
  fi
}

case "${1:-}" in
  human|1)     submit demo/human.json ;;
  uncertain|2) submit demo/uncertain.json save ;;
  ai|3)        submit demo/ai.json ;;
  log)         curl -s "$BASE/log" | python3 -m json.tool ;;
  appeal|4)
    cid=$(cat demo/.content_id)
    curl -s -X POST "$BASE/appeal" -H "Content-Type: application/json" \
      -d "{\"content_id\":\"$cid\",\"creator_id\":\"demo-user\",\"creator_reasoning\":\"I wrote this myself. Non-native speaker — my style may seem formal.\"}" \
      | python3 -m json.tool
    ;;
  *)
    echo "Usage: ./demo.sh {human|uncertain|ai|log|appeal}"
    echo "       ./demo.sh {1|2|3|4}   (same steps)"
    exit 1
    ;;
esac
