#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/srv/lotediretor/app}"
NODE_BIN="${NODE_BIN:-/opt/lotediretor/node22/bin}"
export PATH="$NODE_BIN:$PATH"

cd "$ROOT/apps/client-web"
npm install --no-audit --no-fund
npm run build

cd "$ROOT/services/platform-api"
npm install --no-audit --no-fund
npm run build

install -o root -g root -m 0644   "$ROOT/deploy/vm/systemd/lotediretor-platform-api-v2.service"   /etc/systemd/system/lotediretor-platform-api-v2.service
install -o root -g root -m 0644   "$ROOT/deploy/vm/systemd/lotediretor-client-web-v2.service"   /etc/systemd/system/lotediretor-client-web-v2.service

systemctl daemon-reload
systemctl enable --now lotediretor-platform-api-v2.service
systemctl enable --now lotediretor-client-web-v2.service
systemctl restart lotediretor-platform-api-v2.service
systemctl restart lotediretor-client-web-v2.service

curl -fsS http://127.0.0.1:3000/healthz >/dev/null
curl -fsS http://127.0.0.1:3001/ >/dev/null

echo "LoteDiretor v2 preview healthy on 127.0.0.1:3000/3001"
