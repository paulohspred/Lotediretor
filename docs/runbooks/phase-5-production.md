# Runbook — Fase 5: produção (site, área do cliente, painel admin, IA)

Sobe a pilha completa em um único servidor Linux com Docker. Só o Caddy
(80/443) fica exposto; API, motor, bancos e Martin ficam em redes internas.

| Host              | Serviço                                  |
|-------------------|------------------------------------------|
| `www.` (e apex)   | site institucional (`apps/site-web`)     |
| `app.`            | área do cliente (`apps/client-web`)      |
| `admin.`          | painel administrativo (`apps/admin-web`) |
| `auth.`           | Keycloak (login, MFA)                    |

## 0. Pré-requisitos

- VM com 4 vCPU / 8 GB RAM / 80 GB+ SSD, Docker Engine 24+ e compose v2.
- Registros DNS A/AAAA dos 5 hosts apontando para a VM; portas 80 e 443 abertas.
- O servidor precisa resolver o próprio `auth.` (os apps fazem discovery OIDC
  pela URL pública). Se o provedor não faz *hairpin NAT*, adicione em
  `/etc/hosts` da VM: `127.0.0.1 auth.seudominio.com.br`… e, nos containers,
  use `extra_hosts` com o IP da VM.

```bash
sudo mkdir -p /srv/lotediretor && cd /srv/lotediretor
git clone https://github.com/paulohspred/lotediretor.git app
cd app/deploy/production
cp .env.example .env && chmod 600 .env
```

## 1. Segredos (`.env`)

Gere cada segredo separadamente:

```bash
for v in POSTGRES_PASSWORD APP_DB_PASSWORD KEYCLOAK_DB_PASSWORD KEYCLOAK_ADMIN_PASSWORD \
         CLIENT_SESSION_SECRET ADMIN_SESSION_SECRET LEAD_HASH_SALT \
         CLIENT_OIDC_SECRET ADMIN_OIDC_SECRET; do
  sed -i "s|^$v=.*|$v=$(openssl rand -hex 32)|" .env
done
```

Preencha manualmente: hosts, `ACME_EMAIL`, `ADMIN_ALLOWED_IPS` (IPs do
escritório/VPN), `ANTHROPIC_API_KEY` (opcional — sem ela a A.I Cidades
funciona em modo *somente fontes*), dados da empresa (`COMPANY_*`, `DPO_EMAIL`).

`LEGAL_REVIEWED=true` **só** depois que Política de Privacidade e Termos forem
revisados por advogado; até lá as páginas mostram "Versão preliminar".
Os campos `COMPANY_*`/`LEGAL_REVIEWED` são embutidos no build do site: mudou,
rode `docker compose build site-web`.

Os segredos `CLIENT_OIDC_SECRET`/`ADMIN_OIDC_SECRET` são importados no
Keycloak na primeira subida (realm `lotediretor`). A importação só acontece
se o realm ainda não existe; para trocá-los depois, altere no console do
Keycloak **e** no `.env`.

## 2. Primeira subida

```bash
docker compose --env-file .env up -d --build
docker compose logs -f migrate      # aplica todas as migrations e termina (exit 0)
docker compose ps
```

O `postgres/init.sh` cria (apenas no volume novo) o papel de runtime
`APP_DB_USER`, o banco do Keycloak e define `lotediretor.app_role`, usado pelas
migrations para conceder permissões mínimas. A API e os apps **nunca** usam o
superusuário.

**Banco já existente (migração da VM antiga):** registre as migrations
aplicadas à mão antes do runner e aplique o resto:

```bash
docker compose --profile tools run --rm tools python3 tools/db/migrate.py --baseline 003
docker compose --profile tools run --rm tools python3 tools/db/migrate.py
```

Requer PostgreSQL ≥ 15 com PostGIS.

## 3. Primeiro administrador (Keycloak)

O console do Keycloak (`/admin`) é bloqueado no Caddy. Acesse por túnel SSH:

```bash
# na sua máquina
ssh -L 8080:localhost:8080 usuario@vm
# na VM, exponha temporariamente só em loopback:
docker compose exec keycloak true   # confirma que está rodando
docker run --rm -it --network lotediretor_edge -p 127.0.0.1:8080:8080 alpine/socat \
  tcp-listen:8080,fork,reuseaddr tcp-connect:keycloak:8080
```

Abra `http://localhost:8080/admin`, entre com `KEYCLOAK_ADMIN_USER` /
`KEYCLOAK_ADMIN_PASSWORD` e:

1. Realm **lotediretor** → Users → *Create user* (e-mail verificado).
2. Credentials → defina senha temporária.
3. Role mapping → atribua **platform-admin**.
4. Required actions → **Configure OTP**.
5. Realm settings → Email: configure SMTP (recuperação de senha, verificação).
6. Depois crie um admin pessoal no realm `master` e **desative**
   `bootstrap-admin`.

O cliente `lotediretor-admin` usa um fluxo de login que **sempre** exige
senha + OTP e só ele emite a claim `ld_mfa=true`; a API recusa `/admin/*` sem
papel `platform-admin` e sem MFA. Clientes (área `app.`) se cadastram pela tela
de login; a organização é criada automaticamente no primeiro acesso.

## 4. Carga de dados nacionais

Todos os comandos rodam no container `tools` (tem GDAL, psql e internet):

```bash
T="docker compose --profile tools run --rm tools"

$T tools/loaders/load_ibge_municipal_mesh.sh 2024     # ~5.570 municípios
$T python3 tools/loaders/load_source_registry.py      # catálogo de fontes
$T python3 tools/legal/seed_catalog.py                # Planos Diretores das capitais
```

Verificação rápida: `https://app.…/explorer` → buscar qualquer município →
o cartão de cobertura mostra as fontes; `https://admin.…/cobertura` lista a
cobertura por UF.

## 5. Legislação e regras (por município)

Coloque o PDF/TXT oficial em `/srv/lotediretor/inbox` (montado em `/inbox`):

```bash
$T python3 tools/legal/ingest.py /inbox/lei.pdf --ibge 3505708 ...   # ver phase-4 runbook
```

As regras extraídas entram como **CANDIDATE** e só viram **CONFIRMED** após
revisão humana em `admin.…/regras` (cada decisão exige nota e fica no log de
auditoria imutável). Barueri tem 132 regras candidatas aguardando revisão.

## 6. Fábrica municipal (lotes e zoneamento)

```bash
sudo chown -R 10001 ../../data/connectors/municipal   # container escreve specs
$T python3 tools/factory/discover.py <url-arcgis-ou-wfs> --ibge <codigo> --source-id <id> --write
# revise o JSON gerado em data/connectors/municipal/<ibge>.json, marque status "active"
$T python3 tools/factory/harvest.py <ibge>
git add data/connectors/municipal && git commit -m "data: conector <municipio>"
```

O harvest recusa campos pessoais, exige ≥95% das feições dentro do município e
só troca a carga corrente depois de validar o snapshot.

## 7. Tiles vetoriais (opcional)

Depois de carregar as tabelas referenciadas em `deploy/martin/martin.docker.yaml`:

```bash
docker compose --profile tiles up -d martin
```

## 8. Operação

**Atualizar:**
```bash
cd /srv/lotediretor/app && git pull
cd deploy/production && docker compose --env-file .env up -d --build
```
`migrate` roda a cada `up` e só aplica o que falta (ledger com SHA-256; falha
se uma migration já aplicada foi editada).

**Backup diário** (cron na VM):
```bash
docker compose exec -T postgres pg_dump -U postgres -Fc lotediretor > /srv/backup/ld-$(date +%F).dump
docker compose exec -T postgres pg_dump -U postgres -Fc keycloak    > /srv/backup/kc-$(date +%F).dump
find /srv/backup -name '*.dump' -mtime +14 -delete
```
Copie os dumps para fora da VM (object storage) e teste o restore mensalmente.

**Saúde:** `docker compose ps`; logs em `docker compose logs <serviço>`.
Painel `admin.…/ia` mostra uso e feedback da A.I Cidades; `admin.…/auditoria`
mostra toda ação administrativa.

## 9. Checklist de go-live

- [ ] `.env` com segredos únicos, `chmod 600`, fora do git
- [ ] `ADMIN_ALLOWED_IPS` restrito
- [ ] Admin com OTP criado; `bootstrap-admin` desativado
- [ ] SMTP do Keycloak configurado e testado
- [ ] Malha IBGE carregada (≈5.570 municípios em `/admin/cobertura`)
- [ ] Textos legais revisados → `LEGAL_REVIEWED=true` + rebuild do site
- [ ] Backup + restore testados
- [ ] `ANTHROPIC_API_KEY` definida (ou modo somente-fontes aceito)
