# Conectores municipais (fábrica de municípios)

Cada arquivo `<ibge>.json` descreve **onde** um município publica suas camadas
(lotes, zoneamento) e **como** os campos viram o esquema nacional. Adicionar
um município é revisar um JSON, não escrever código.

## Fluxo (Blueprint §7 e §19)

1. **Descobrir** (no servidor, que acessa a internet):
   ```bash
   python3 tools/factory/discover.py --ibge 4209102 \
     --source-id sc-joinville-simgeo-arcgis \
     https://geo.joinville.sc.gov.br/server/rest/services --write
   ```
   Gera um rascunho `DRAFT` com a camada mais provável, o mapeamento de campos
   e a lista de campos pessoais que foram **excluídos**.
2. **Revisar** (pessoa): conferir camada, campos, `min_features`, preencher
   `license` com os termos da fonte, `reviewed_by`, `reviewed_at` e mudar
   `status` para `APPROVED`. Abrir PR — o CI valida o spec.
3. **Carregar**:
   ```bash
   LOTEDIRETOR_DB_DSN=... python3 tools/factory/harvest.py 4209102
   ```
   O harvester pede ao servidor municipal apenas os campos mapeados, verifica
   que ≥ 95% das feições caem dentro do município (pega camada ou CRS
   errados), grava snapshot com hash e só então troca a carga atual.
4. **Verificar** no Explorer: o município passa a abrir o lote pelo clique.

## Regras

- Campos com cara de dado pessoal (proprietário, contribuinte, CPF/CNPJ,
  telefone, e-mail…) são bloqueados pelo validador, mesmo se publicados.
- Sem `license` preenchida o spec não é aceito.
- URLs remotas precisam ser `https`.
- Parâmetros urbanísticos (CA, TO, recuos) **não** vêm daqui: dependem do
  motor jurídico (Fase 4). O dossiê diz isso explicitamente.

## Formato

```json
{
  "municipality_ibge": "4209102",
  "status": "APPROVED",
  "reviewed_by": "nome",
  "reviewed_at": "2026-10-01",
  "layers": [
    {
      "role": "parcels",
      "source_id": "sc-joinville-simgeo-arcgis",
      "kind": "arcgis_feature_layer",
      "url": "https://.../MapServer/12",
      "license": "Termos de uso do portal, consultados em 2026-10-01",
      "fields": {
        "upstream_key": "OBJECTID",
        "fiscal_reference": "INSCRICAO",
        "street": "LOGRADOURO",
        "house_number": "NUMERO",
        "neighborhood": "BAIRRO",
        "land_area_m2": "AREA_TERRENO"
      },
      "attribute_allowlist": ["QUADRA", "LOTE"],
      "min_features": 1000
    },
    {
      "role": "zoning",
      "source_id": "sc-joinville-simgeo-arcgis",
      "kind": "ogc_wfs",
      "url": "https://.../wfs",
      "type_name": "planejamento:zoneamento",
      "license": "…",
      "fields": { "upstream_key": "fid", "zone_code": "sigla", "zone_name": "nome" },
      "min_features": 5
    }
  ]
}
```

`kind`: `arcgis_feature_layer`, `ogc_wfs` ou `file` (GPKG/SHP/GeoJSON local
ou via https). `source_srid` opcional quando o serviço não declara o CRS.
