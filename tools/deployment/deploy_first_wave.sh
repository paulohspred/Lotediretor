#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/srv/lotediretor/app}"
RUNTIME_SERVICES="${RUNTIME_SERVICES:-/srv/lotediretor/services}"
SERVICE_NAME="${SERVICE_NAME:-lotediretor-parcel-api.service}"
WEB_ROOT="${WEB_ROOT:-$APP_ROOT/dist/lotediretor}"

cd "$APP_ROOT"

echo "[1/7] validating repository artifacts"
python3 - <<'PY'
import json
from pathlib import Path
json.load(open("data/deployment/professional-completion-matrix.json", encoding="utf-8"))
json.load(open("data/source-registry/bootstrap.json", encoding="utf-8"))
s=Path("public/lotediretor/index.html").read_text(encoding="utf-8")
start=s.index("<script>")+len("<script>")
end=s.rindex("</script>")
Path("/tmp/lotediretor-ui.js").write_text(s[start:end], encoding="utf-8")
print("json=ok")
PY
node --check /tmp/lotediretor-ui.js
python3 tools/regression/audit_frontend.py

echo "[2/7] compiling parcel services"
python3 -m py_compile   services/demo_parcel_api.py   services/recife_property.py   services/rio_property.py   services/bh_property.py   services/joao_pessoa_property.py   services/municipality_utilities.py

echo "[3/7] syncing runtime services"
for file in   demo_parcel_api.py   recife_property.py   rio_property.py   bh_property.py   joao_pessoa_property.py   municipality_utilities.py   postgis_store.py   recife_index.py
do
  if [[ -f "services/$file" ]]; then
    sudo install -o root -g root -m 0644 "services/$file" "$RUNTIME_SERVICES/$file"
  fi
done

echo "[4/7] syncing web artifact"
sudo mkdir -p "$WEB_ROOT"
sudo install -o sentinelx -g sentinelx -m 0664   public/lotediretor/index.html   "$WEB_ROOT/index.html"

echo "[5/7] restarting API"
sudo systemctl restart "$SERVICE_NAME"
for attempt in 1 2 3 4 5 6 7 8; do
  if curl -fsS --max-time 5 http://127.0.0.1:8765/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 5 http://127.0.0.1:8765/healthz >/dev/null
sudo systemctl is-active --quiet "$SERVICE_NAME"
sudo systemctl is-active --quiet nginx

echo "[6/7] running first-wave regression"
python3 tools/regression/smoke_first_wave.py

echo "[7/7] verifying served artifact"
src_hash="$(sha256sum public/lotediretor/index.html | awk '{print $1}')"
dist_hash="$(sha256sum "$WEB_ROOT/index.html" | awk '{print $1}')"
if [[ "$src_hash" != "$dist_hash" ]]; then
  echo "frontend hash mismatch" >&2
  exit 1
fi

rm -rf services/__pycache__ tools/ingestion/__pycache__ tools/regression/__pycache__
echo "DEPLOY PASSED"
echo "commit=$(git rev-parse HEAD)"
