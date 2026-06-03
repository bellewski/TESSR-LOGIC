#!/usr/bin/env bash
# TESSR-LOGIC — quick health check of the running backend + capabilities.
# Run from repo root after ./update.sh:  ./verify.sh
BASE="${BASE:-http://localhost:8000}"
pass=0; fail=0
ck() { # ck "label" "url" [expected_substring]
  local label="$1" url="$2" want="${3:-}"
  local body code
  body=$(curl -s -m 10 -w $'\n%{http_code}' "$url" 2>/dev/null)
  code=$(echo "$body" | tail -1)
  if [ "$code" = "200" ] && { [ -z "$want" ] || echo "$body" | grep -q "$want"; }; then
    echo "  [ok]  $label"; pass=$((pass+1))
  else
    echo "  [FAIL $code] $label  ($url)"; fail=$((fail+1))
  fi
}

echo "==> backend @ $BASE"
ck "API up (docs)"          "$BASE/docs"
ck "builds list"            "$BASE/api/builds?limit=1"
ck "agents (incl. design_critic)" "$BASE/api/agents" "design_critic"
ck "brand kits (>=11)"      "$BASE/api/brand-kits" "tessr-logic"
ck "library (recipes)"      "$BASE/api/library" "hero-bento-glass"
ck "library search"         "$BASE/api/library/search?q=hero+bento&k=2" "exemplar"
ck "plugins (output/deploy)" "$BASE/api/plugins" "zip"
ck "connectors list"        "$BASE/api/connectors"

echo "==> capabilities (optional power-ups)"
if command -v ollama >/dev/null 2>&1; then
  ollama list 2>/dev/null | grep -qi nomic && echo "  [ok]  learning memory (nomic-embed-text)" || echo "  [off] learning memory — run ./powerup.sh"
  ollama list 2>/dev/null | grep -qiE "llava|moondream|vl|vision" && echo "  [ok]  vision model present" || echo "  [off] vision model — run ./powerup.sh"
else
  echo "  [??]  ollama not on PATH"
fi
python -c "import playwright" 2>/dev/null && echo "  [ok]  playwright (vision render)" || echo "  [off] playwright — run ./powerup.sh"

echo
echo "==> $pass passed, $fail failed"
[ "$fail" = "0" ] && echo "All endpoints healthy." || echo "Some checks failed — see tail -40 tessr.log"
