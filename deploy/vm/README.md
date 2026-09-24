# LoteDiretor — VM deployment

Minimal clean deployment for the first LoteDiretor/ZoLa pilot.

## Recommended first VM

For the first 5-city pilot:

- Ubuntu 24.04 LTS;
- 8 vCPU;
- 32 GB RAM;
- 300–500 GB NVMe;
- public IPv4;
- ports 22, 80 and 443;
- daily provider snapshot/backup.

For national growth, raw GIS/raster snapshots should move to S3-compatible object storage rather than consuming the VM disk.

## Services

- `zola`: current Ember ZoLa production build served by nginx;
- `postgres`: PostgreSQL 16 + PostGIS;
- `caddy`: TLS/reverse proxy.

Martin/vector tiles and the normalized LoteDiretor API are deliberately not included yet. They should be introduced after the first municipal connectors and schema are materialized.

## Install

Create a fresh Ubuntu VM, connect it to SentinelX, then the deployment can be executed/verified remotely.

Manual bootstrap:

```bash
git clone https://github.com/paulohspred/Lotediretor.git /srv/lotediretor
cd /srv/lotediretor
sudo bash deploy/vm/bootstrap.sh

cd /srv/lotediretor/deploy/vm
sudo nano .env
sudo docker compose build
sudo docker compose up -d
```

## Secrets

Do not commit `.env`.

The PostgreSQL password is generated during bootstrap if `.env` does not exist.

A Mapbox public token is currently a build-time setting inherited from ZoLa. Longer term the national frontend should use MapLibre with basemaps whose licensing fits LoteDiretor.

## Rollout

Start with:

1. São Paulo;
2. Recife;
3. Rio de Janeiro;
4. Belo Horizonte;
5. João Pessoa.

Validate the normalized property/zoning contract, then enable the remaining cities listed in `data/deployment/readiness.json`.
