#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/paulohspred/Lotediretor.git}"
APP_DIR="${APP_DIR:-/srv/lotediretor}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/vm/bootstrap.sh"
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl git openssl

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

if [[ ! -d "${APP_DIR}/.git" ]]; then
  git clone "${REPO_URL}" "${APP_DIR}"
else
  git -C "${APP_DIR}" fetch origin
  git -C "${APP_DIR}" checkout main
  git -C "${APP_DIR}" pull --ff-only origin main
fi

cd "${APP_DIR}/deploy/vm"

if [[ ! -f .env ]]; then
  cp .env.example .env
  DB_PASSWORD="$(openssl rand -hex 32)"
  sed -i "s#CHANGE_ME_WITH_A_LONG_RANDOM_PASSWORD#${DB_PASSWORD}#" .env
  echo "Created deploy/vm/.env with a random PostgreSQL password."
  echo "Review DOMAIN and MAPBOX_ACCESS_TOKEN before production use."
fi

docker compose config >/dev/null

echo
echo "Bootstrap complete."
echo "Next:"
echo "  cd ${APP_DIR}/deploy/vm"
echo "  edit .env"
echo "  docker compose build"
echo "  docker compose up -d"
