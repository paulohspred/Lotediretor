# Source discovery tools

Ferramentas de descoberta para interfaces públicas e documentadas. A saída é metadado/candidato para revisão — **não** autorização automática para ingestão ou redistribuição.

## harvest.py

Modos atuais:

- `ckan` — pesquisa de datasets/resources em CKAN;
- `arcgis` — inspeciona diretório, serviço ou layer ArcGIS REST;
- `arcgis-tree` — percorre pastas de um ArcGIS REST de forma limitada;
- `wfs` — lê `GetCapabilities` e enumera feature types;
- `directory` — enumera diretórios HTTP públicos na mesma origem sem baixar os arquivos-alvo;
- `sapl` — consulta GETs públicos da API REST do SAPL/Interlegis;
- `lexml` — pesquisa o endpoint SRU oficial do LexML e extrai metadados/URNs.

O modo ArcGIS possui uma heurística que marca campos potencialmente pessoais/restritos, como CPF/CNPJ, proprietário, titular, requerente, documento, telefone e e-mail. Isso é um **alerta de revisão**, não uma classificação jurídica automática.

## Exemplos

```bash
# CKAN
python tools/discovery/harvest.py ckan https://dados.recife.pe.gov.br --query IPTU

# ArcGIS
python tools/discovery/harvest.py arcgis \
  https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Fazenda/ITBI/MapServer

python tools/discovery/harvest.py arcgis-tree \
  https://gis-smamus.portoalegre.rs.gov.br/server/rest/services \
  --max-depth 2 --max-nodes 200

# WFS / GeoServer
python tools/discovery/harvest.py wfs \
  https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs

# Diretório público: registra links; não baixa ZIPs/SHPs
python tools/discovery/harvest.py directory \
  https://geoftp.ibge.gov.br/organizacao_do_territorio/ \
  --max-depth 1 --max-items 1000

# SAPL
python tools/discovery/harvest.py sapl \
  https://sapl.pains.mg.leg.br \
  --endpoint norma/normajuridica \
  --max-pages 3

python tools/discovery/harvest.py sapl \
  https://sapl.pains.mg.leg.br \
  --endpoint norma/normarelacionada \
  --max-pages 2

# LexML / CQL
python tools/discovery/harvest.py lexml \
  --query 'urn any plano and description any diretor' \
  --maximum-records 50

python tools/discovery/harvest.py lexml \
  --query 'urn any lei and date any 2026' \
  --maximum-records 100
```

## Fluxo esperado

1. descobrir a fonte;
2. identificar autoridade e cobertura;
3. localizar documentação/licença/termos;
4. classificar acesso;
5. inspecionar schema e campos pessoais;
6. registrar no Source Registry;
7. só então construir o conector/materialização;
8. salvar snapshot, hash, timestamp, parser e lineage.

## Limites

Não usar estas ferramentas para:

- contornar autenticação, CAPTCHA ou paywall;
- tentar endpoints privados/administrativos;
- baixar em massa conteúdo sem verificar licença;
- republicar dados pessoais porque um endpoint público os expôs;
- raspar Google Maps ou Street View;
- seguir diretórios públicos para outra origem automaticamente;
- tratar um endpoint não documentado como contrato estável de produção.

Para legislação, o objetivo é ligar **norma → publicação oficial → anexos → alterações/vínculos → geometria → regra estruturada**, mantendo sempre a fonte primária.
