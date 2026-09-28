#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/srv/lotediretor/app}"
NODE_BIN="${NODE_BIN:-/opt/lotediretor/node22/bin}"
MARTIN_BIN="${MARTIN_BIN:-/opt/lotediretor/martin/martin}"

if [[ ! -x "$NODE_BIN/node" ]]; then
  bash "$ROOT/deploy/vm/install-node22.sh"
fi
if [[ ! -x "$MARTIN_BIN" ]]; then
  bash "$ROOT/deploy/vm/install-martin.sh"
fi

export PATH="$NODE_BIN:$PATH"

cd "$ROOT/apps/client-web"
npm install --no-audit --no-fund
npm run build

cd "$ROOT/services/platform-api"
npm install --no-audit --no-fund
npm run build

for unit in   lotediretor-martin-v2.service   lotediretor-platform-api-v2.service   lotediretor-client-web-v2.service; do
  install -o root -g root -m 0644     "$ROOT/deploy/vm/systemd/$unit"     "/etc/systemd/system/$unit"
done

systemctl daemon-reload
systemctl enable --now lotediretor-martin-v2.service
systemctl enable --now lotediretor-platform-api-v2.service
systemctl enable --now lotediretor-client-web-v2.service

systemctl restart lotediretor-martin-v2.service
systemctl restart lotediretor-platform-api-v2.service
systemctl restart lotediretor-client-web-v2.service

curl -fsS http://127.0.0.1:3002/health >/dev/null
curl -fsS http://127.0.0.1:3000/healthz >/dev/null
curl -fsS http://127.0.0.1:3001/ >/dev/null

echo "LoteDiretor v2 preview healthy: Martin 3002, API 3000, Web 3001"
