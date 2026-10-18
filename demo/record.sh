#!/usr/bin/env bash
# Usage:
#   ./demo/record.sh <beat> [checkpoint] [--check|--run]
# Examples:
#   ./demo/record.sh 02-answer-route clean --check
#   ./demo/record.sh 02-answer-route clean
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BEAT="${1:?Usage: ./demo/record.sh <beat> [checkpoint] [--check|--run]}"
BEAT="${BEAT%.json}"
BEAT="${BEAT#demo/beats/}"
BEAT="${BEAT#beats/}"

# Default checkpoint mapping per beat if omitted
default_checkpoint_for() {
  case "$1" in
    00-*)      echo "empty" ;;
    01-*|02-*) echo "clean" ;;
    03-*)      echo "ticket-routed" ;;
    04-*|05-*|06-*|07-*) echo "post-reorg" ;;
    *)         echo "clean" ;;
  esac
}

CHECKPOINT="${2:-$(default_checkpoint_for "$BEAT")}"
MODE="${3:---run}"
if [[ "$CHECKPOINT" == "--check" || "$CHECKPOINT" == "--run" ]]; then
  MODE="$CHECKPOINT"
  CHECKPOINT="$(default_checkpoint_for "$BEAT")"
fi

STEPS_FILE="demo/beats/${BEAT}.json"
if [[ ! -f "$STEPS_FILE" ]]; then
  echo "Error: steps file not found: $STEPS_FILE" >&2
  exit 1
fi

# Discover local API and UI ports (never touch port 8000)
API_PORT="${API_PORT:-8011}"
UI_PORT="${UI_PORT:-3000}"
API_BASE="${API_BASE:-http://localhost:${API_PORT}}"
UI_BASE="${UI_BASE:-http://localhost:${UI_PORT}}"
ADMIN_TOKEN="${ADMIN_TOKEN:-rec-admin-local}"
PROFILE_NAME="${CURSORCAM_PROFILE:-nodus-demo}"

if ! curl -sf "${API_BASE}/health" >/dev/null; then
  echo "Error: local API is not reachable at ${API_BASE}/health" >&2
  exit 1
fi
if ! curl -sf "${UI_BASE}/login" >/dev/null; then
  echo "Error: local UI is not reachable at ${UI_BASE}/login" >&2
  exit 1
fi

# 1. Log in as the recording account, write CursorCam storageState profile, and reset to checkpoint
WORKSPACE="$(
  API_BASE="$API_BASE" UI_BASE="$UI_BASE" ADMIN_TOKEN="$ADMIN_TOKEN" CHECKPOINT="$CHECKPOINT" PROFILE_NAME="$PROFILE_NAME" \
  .venv/bin/python - <<'PY'
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import httpx

api_base = os.environ["API_BASE"]
ui_base = os.environ["UI_BASE"]
admin_token = os.environ["ADMIN_TOKEN"]
checkpoint = os.environ["CHECKPOINT"]
profile_name = os.environ["PROFILE_NAME"]

cache_dir = Path(os.environ.get("CURSORCAM_CACHE_DIR") or Path.home() / "Library/Caches/cursorcam")
saved_profiles = cache_dir / "saved-profiles"
saved_profiles.mkdir(parents=True, exist_ok=True)

profile_path = saved_profiles / f"{profile_name}.json"

with httpx.Client(base_url=api_base, timeout=30.0) as client:
    me = None
    if profile_path.exists():
        try:
            existing = json.loads(profile_path.read_text())
            for c in existing.get("cookies", []):
                client.cookies.set(c["name"], c["value"])
            r = client.get("/auth/me")
            if r.status_code == 200 and r.json().get("account"):
                me = r.json()
        except Exception:
            me = None

    if not me:
        r = client.post("/auth/demo")
        r.raise_for_status()
        me = r.json()

    ws_name = me["account"]["workspace"]

    # Reset workspace to the requested checkpoint
    rst = client.post(
        "/admin/reset",
        json={"checkpoint": checkpoint, "workspace": ws_name},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    rst.raise_for_status()

    host = urlparse(ui_base).hostname or "localhost"
    cookies = []
    for c in client.cookies.jar:
        cookies.append({
            "name": c.name,
            "value": c.value,
            "domain": host,
            "path": c.path or "/",
            "expires": -1,
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax",
        })

    storage_state = {
        "cookies": cookies,
        "origins": [
            {
                "origin": ui_base,
                "localStorage": [
                    {"name": "nodus.theme", "value": "dark"},
                ],
            }
        ],
    }
    profile_path.write_text(json.dumps(storage_state, indent=2))
    os.chmod(profile_path, 0o600)
    print(ws_name)
PY
)"

echo "[record.sh] beat=${BEAT} checkpoint=${CHECKPOINT} workspace=${WORKSPACE} ui=${UI_BASE} api=${API_BASE} mode=${MODE}"

PROFILE_ARGS=(--profile "$PROFILE_NAME")
if [[ "$BEAT" == 00-* ]]; then
  PROFILE_ARGS=()
fi

if [[ "$MODE" == "--check" ]]; then
  npx cursorcam check "$STEPS_FILE" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"}
  exit 0
fi

# 2. Record and render MP4
OUT_JSON="$(npx cursorcam run "$STEPS_FILE" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} --style demo/style.json --for youtube --json)"
echo "$OUT_JSON"

RUN_DIR="$(
  OUT_JSON="$OUT_JSON" .venv/bin/python - <<'PY'
import json, os
data = json.loads(os.environ["OUT_JSON"])
print(data.get("run") or data.get("runDir") or "")
PY
)"

if [[ -n "$RUN_DIR" && -d "$RUN_DIR" ]]; then
  npx cursorcam stills "$RUN_DIR"
fi

OUT_JSON="$OUT_JSON" .venv/bin/python - <<'PY'
import json, os
data = json.loads(os.environ["OUT_JSON"])
run_dir = data.get("run") or data.get("runDir") or ""
dur_s = float(data.get("durationSeconds") or 0.0)
mins = int(dur_s // 60)
secs = dur_s - mins * 60
print(f"[duration] beat_seconds={dur_s:.2f}s ({mins}:{secs:04.1f}) run_dir={run_dir}", flush=True)
PY

