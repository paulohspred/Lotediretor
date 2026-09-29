# Runbook — Fase 2: base territorial nacional

Aplica no servidor de produção (VM) a base de municípios do IBGE e o catálogo
de fontes consultável. Todos os passos são idempotentes.

## 1. Migrations

```bash
cd /srv/lotediretor/app
export LOTEDIRETOR_DB_DSN="postgresql:///lotediretor?host=/var/run/postgresql"

# Apenas na PRIMEIRA vez: registra 001–003, aplicadas à mão antes do runner.
sudo -u postgres env LOTEDIRETOR_DB_DSN="$LOTEDIRETOR_DB_DSN" \
  python3 tools/db/migrate.py --baseline 003

sudo -u postgres env LOTEDIRETOR_DB_DSN="$LOTEDIRETOR_DB_DSN" \
  python3 tools/db/migrate.py          # aplica 004
```

## 2. Malha municipal do IBGE (≈5.570 municípios)

Requer `gdal-bin`. Baixa o arquivo oficial, grava snapshot com SHA-256 e só
troca os dados se todas as checagens passarem (contagem, códigos, UFs).

```bash
sudo apt-get install -y gdal-bin
sudo -u postgres env LOTEDIRETOR_DB_DSN="$LOTEDIRETOR_DB_DSN" \
  tools/loaders/load_ibge_municipal_mesh.sh 2024
```

Se o servidor não acessar o IBGE, baixe `BR_Municipios_2024.zip` em outra
máquina e rode com `MESH_FILE=/caminho/BR_Municipios_2024.zip`.

## 3. Catálogo de fontes no banco

```bash
sudo -u postgres env LOTEDIRETOR_DB_DSN="$LOTEDIRETOR_DB_DSN" \
  python3 tools/loaders/load_source_registry.py
```

Repita sempre que `data/source-registry/bootstrap.json` mudar.

## 4. API e web

```bash
bash deploy/vm/deploy-v2-preview.sh
curl -s "http://127.0.0.1:3000/municipalities/resolve?lat=-22.25&lng=-45.70"
curl -s "http://127.0.0.1:3000/municipalities/3159605/coverage" | head -c 400
```

A unit `lotediretor-platform-api-v2.service` agora define `DATABASE_URL`
(papel `sentinelx`, somente leitura nas tabelas territoriais).

## Verificação

- `resolve` para um ponto no mar retorna 404 `MUNICIPALITY_NOT_FOUND`.
- No Explorer, busque qualquer município pelo nome; o painel "Cobertura de
  dados" mostra fontes federais, estaduais e municipais catalogadas.
