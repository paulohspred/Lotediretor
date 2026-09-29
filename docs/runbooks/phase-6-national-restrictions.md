# Runbook — Fase 6: camada nacional de restrições

A Fase 6 materializa camadas nacionais oficiais em PostGIS, sempre em SRID 4674,
com snapshot imutável e promoção somente após validação. Nenhuma camada permite
inferir propriedade, titularidade, licença ou capacidade de infraestrutura por
mera proximidade.

## Fontes e formatos

| Camada | Órgão | Endpoint oficial | Formato |
|---|---|---|---|
| Terras indígenas | FUNAI | `geoserver.funai.gov.br/geoserver/Funai/ows` / página oficial de geoprocessamento | SHP-ZIP / WFS |
| Unidades de conservação | MMA/CNUC | recurso versionado do Portal de Dados Abertos MMA | SHP-ZIP |
| Processos minerários | ANM/SIGMINE | `dadosabertos.anm.gov.br/SIGMINE/PROCESSOS_MINERARIOS/BRASIL.zip` | SHP-ZIP |
| Hidrografia BHO 2017 | ANA/SNIRH | `www.snirh.gov.br/arcgis/rest/services/SPR/BHO2017_50K_TRECHODRENAGEM/FeatureServer/0` | ArcGIS REST / GeoJSON |
| Áreas de drenagem BHO 2017 | ANA/SNIRH | `www.snirh.gov.br/arcgis/rest/services/SPR/BHO2017_50K_AREADRENAGEM/FeatureServer/0` | ArcGIS REST / GeoJSON |
| PRODES | INPE/TerraBrasilis | `terrabrasilis.dpi.inpe.br/downloads/` | GeoPackage oficial |
| DETER | INPE/TerraBrasilis | `terrabrasilis.dpi.inpe.br/downloads/` | SHP-ZIP oficial |
| Linhas de transmissão | ANEEL/GCEM | recurso CSV do portal de dados abertos | CSV |
| Subestações | ANEEL/GCEM | recurso CSV do portal de dados abertos | CSV |
| Bens protegidos | IPHAN/SICG | `geoserver.iphan.gov.br/geoserver/SICG/ows`, camada `SICG:Bem_Protecao` | WFS / GeoJSON |
| Setorização de risco | SGB | `geoportal.sgb.gov.br/.../gestaoterritorial/risco/FeatureServer/0` | ArcGIS REST / GeoJSON |
| Geologia | SGB/GeoSGB | `geosgb.sgb.gov.br/downloads/` | SHP-ZIP oficial |

O arquivo versionado `data/restrictions/layers.json` é a configuração operacional.
PRODES, DETER e geologia SGB exigem seleção explícita do arquivo oficial, porque
o portal publica múltiplos produtos/recortes. A carga não escolhe silenciosamente
um produto em nome do operador.

Os CSVs GCEM da ANEEL são snapshotados, mas ficam
`NOT_AVAILABLE_SPATIAL` enquanto não houver coordenada/traçado oficial
suficiente no recurso utilizado. Não é permitido geocodificar nomes de
subestações ou linhas para inventar geometria.

## 1. Migration

```bash
export LOTEDIRETOR_DB_DSN="postgresql:///lotediretor?host=/var/run/postgresql"
python3 tools/db/migrate.py
```

A migration `009_national_restrictions.sql` cria:

- `ld_core.restriction_layer`;
- `ld_core.restriction_feature`;
- índices GiST;
- `ld_api.current_restriction_feature`;
- funções de interseção/distância para ponto e geometria.

A migration `010_national_restrictions_hardening.sql` adiciona índice GiST sobre `geography`, preserva múltiplas interseções por camada e remove privilégio de sequência desnecessário do papel de runtime.

O container `tools` de produção monta `/var/cache/lotediretor/restrictions` em `RESTRICTION_SNAPSHOT_DIR` no host. Antes da primeira carga, crie o diretório com o UID do container:

```bash
sudo install -d -o 10001 -g 10001 /srv/lotediretor/snapshots/restrictions
```

Não apague esse diretório durante deploys: ele contém os arquivos brutos cujos SHA-256 estão registrados em `ld_catalog.snapshot`. Fontes explicitamente marcadas com `retain_raw=false` registram o hash e os metadados, mas não retêm o bruto local.

## 2. Publicar o catálogo e registrar todas as camadas

```bash
python3 tools/loaders/load_source_registry.py
python3 tools/loaders/load_national_restrictions.py --all --register-only
```

Isso faz o painel admin mostrar inclusive camadas ainda não carregadas.

## 3. Cargas automáticas

Execute uma camada por vez para facilitar auditoria:

```bash
python3 tools/loaders/load_national_restrictions.py cnuc_conservation_units
python3 tools/loaders/load_national_restrictions.py anm_mining_processes
python3 tools/loaders/load_national_restrictions.py ana_hydrography_bho2017
python3 tools/loaders/load_national_restrictions.py ana_hydrographic_basins_bho2017
python3 tools/loaders/load_national_restrictions.py iphan_protected_assets
python3 tools/loaders/load_national_restrictions.py sgb_geological_risk
python3 tools/loaders/load_national_restrictions.py aneel_transmission_lines
python3 tools/loaders/load_national_restrictions.py aneel_substations
python3 tools/loaders/load_national_restrictions.py funai_indigenous_lands
```

Se uma fonte oficial estiver temporariamente bloqueada/fora do ar, o status é
`SOURCE_UNAVAILABLE`; a carga anterior continua corrente.

## 4. Arquivos oficiais selecionados manualmente

Baixe o produto desejado diretamente do portal oficial e passe o arquivo sem
alterá-lo. O SHA-256 registrado é do arquivo bruto recebido.

```bash
python3 tools/loaders/load_national_restrictions.py inpe_prodes --file /inbox/prodes.gpkg
python3 tools/loaders/load_national_restrictions.py inpe_deter --file /inbox/deter.zip
python3 tools/loaders/load_national_restrictions.py sgb_geology --file /inbox/geologia.zip
```

## 5. Garantias de ingestão

- snapshot registra URL, órgão, data de coleta, licença declarada/configurada e SHA-256;
- ArcGIS guarda um bundle das respostas brutas paginadas; o GeoJSON agregado é apenas artefato de importação;
- CPF/CNPJ e chaves contendo proprietário/titular/owner são removidos dos atributos normalizados;
- geometria inválida ou SRID incorreto impede promoção;
- a carga corrente só muda após validar toda a staging;
- falha não apaga a carga corrente anterior;
- a carga ANM exclui a coluna `NOME` da normalização e não retém o bruto local após registrar o SHA-256.

## 6. Consulta no dossiê

`services/point_context.py` consulta as camadas ativas no PostGIS e retorna as
interseções encontradas (até 20 por camada) ou, quando não há interseção, a
feição mais próxima dentro do raio configurado, indicando:

- interseção com a área analisada, ou distância em metros;
- órgão-fonte;
- data da carga;
- data da fonte, quando publicada.

Para municípios com lote materializado pela fábrica, o
`FactoryParcelService` calcula a relação usando a geometria real do lote, não
o buffer do ponto.

## 7. Painel administrativo

`/cobertura` exibe uma tabela de camadas nacionais com status, quantidade de
feições, última carga e atualização declarada pela fonte, além da cobertura
municipal existente.

## 8. Testes

```bash
python3 -m unittest discover -s services/tests -v
python3 -m unittest discover -s tools/restrictions/tests -v

cd services/platform-api
npm run typecheck
npm test

cd ../../../apps/admin-web
npx tsc --noEmit
npm run lint
npm run build
```

O teste de banco da camada nacional valida snapshot, promoção, interseção
espacial e remoção de campo pessoal.
