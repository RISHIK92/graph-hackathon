#!/usr/bin/env bash
# deploy/smoke.sh <https://subdomain>: health, one cited answer, an anonymous write refused, the token check, TLS.
set -u
URL="${1:?usage: deploy/smoke.sh https://<subdomain>}"
API="$URL/api"
fail=0
check() { if [ "$2" = "0" ]; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

curl -fsS --max-time 10 "$URL" -o /dev/null; check "TLS: $URL serves a valid certificate" $?
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://${URL#https://}")
[ "$code" = "308" ] || [ "$code" = "301" ]; check "HTTP redirects to HTTPS ($code)" $?

ok=$(curl -fsS --max-time 10 "$API/health" | json 'd.get("ok")')
[ "$ok" = "True" ]; check "health" $?

sid=$(curl -fsS --max-time 10 -X POST "$API/sessions" -H 'Content-Type: application/json' -d '{}' | json 'd["session_id"]')
ans=$(curl -fsS --max-time 60 -X POST "$API/sessions/$sid/turns/sync" -H 'Content-Type: application/json' \
      -d '{"text": "Who owns Ledger?"}')
cited=$(echo "$ans" | json 'next(e for e in d["events"] if e["event"] == "answer") and sum(len(c.get("span_ids") or []) for c in next(e for e in d["events"] if e["event"] == "answer")["claims"])')
[ "${cited:-0}" -gt 0 ] 2>/dev/null; check "a cited answer ($cited citations)" $?

wr=$(curl -fsS --max-time 60 -X POST "$API/sessions/$sid/turns/sync" -H 'Content-Type: application/json' \
     -d '{"text": "Infra owns Ledger now"}' | json '[e.get("status") for e in d["events"] if e["event"] == "action"]')
echo "$wr" | grep -q needs_token; check "an anonymous write is refused (needs_token)" $?

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST "$API/admin/reset")
[ "$code" = "401" ]; check "admin without a token is refused ($code)" $?
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST "$API/admin/reset" -H 'Authorization: Bearer wrong-token')
[ "$code" = "401" ]; check "a wrong token is refused ($code)" $?

exit $fail
