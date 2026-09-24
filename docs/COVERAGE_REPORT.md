# Coverage Report — Source Registry

**Data:** 24/09/2026  
**Fontes-mãe:** 169  
**Municípios com ao menos uma fonte municipal identificada:** 50

Este relatório é calculado a partir de `data/source-registry/bootstrap.json`. Presença de domínio não implica completude, licença para redistribuição ou qualidade suficiente.

## Domínios-chave

`cadastre`, `lots`, `buildings`, `iptu`, `itbi`, `plan_director`, `zoning`, `urban_planning`, `building_permits`, `licensing`, `habite_se`, `imagery`, `terrain`, `risk`, `environment`, `heritage`, `official_gazette`

## UFs com maior lacuna operacional

| UF | Fontes | Municípios | Domínios-chave presentes | Faltantes |
|---|---:|---:|---:|---:|
| RR | 1 | 1 | 1/17 | 16 |
| MT | 2 | 1 | 2/17 | 15 |
| AP | 1 | 1 | 3/17 | 14 |
| AL | 2 | 1 | 3/17 | 14 |
| RO | 2 | 1 | 3/17 | 14 |
| RN | 1 | 1 | 4/17 | 13 |
| PI | 2 | 1 | 4/17 | 13 |
| BA | 3 | 1 | 4/17 | 13 |
| PA | 3 | 1 | 4/17 | 13 |
| DF | 2 | 0 | 5/17 | 12 |
| SE | 2 | 1 | 5/17 | 12 |
| TO | 2 | 1 | 5/17 | 12 |
| GO | 4 | 1 | 5/17 | 12 |
| AC | 2 | 1 | 6/17 | 11 |
| AM | 2 | 1 | 6/17 | 11 |

## Regra de prioridade

Uma UF/capital não é considerada operacionalmente coberta apenas por possuir Plano Diretor ou portal cartográfico.

1. cadastro/lote/edificação;
2. IPTU/ITBI/PGV;
3. zoneamento/Plano Diretor com vigência;
4. licenciamento, alvará e habite-se;
5. imagem/ortofoto/topografia;
6. risco, ambiente e patrimônio;
7. Diário Oficial e histórico normativo.

## Próxima fila orientada por lacunas

- **RR** — faltam: cadastre, lots, buildings, iptu, itbi, plan_director, zoning, building_permits, licensing, habite_se, imagery, terrain, risk, environment, heritage, official_gazette.
- **MT** — faltam: cadastre, lots, buildings, iptu, itbi, plan_director, urban_planning, building_permits, licensing, habite_se, imagery, terrain, risk, heritage, official_gazette.
- **AP** — faltam: lots, buildings, iptu, zoning, urban_planning, building_permits, licensing, habite_se, imagery, terrain, risk, environment, heritage, official_gazette.
- **AL** — faltam: buildings, iptu, itbi, plan_director, urban_planning, building_permits, licensing, habite_se, imagery, terrain, risk, environment, heritage, official_gazette.
- **RO** — faltam: lots, buildings, iptu, itbi, plan_director, building_permits, licensing, habite_se, imagery, terrain, risk, environment, heritage, official_gazette.
- **RN** — faltam: cadastre, lots, buildings, iptu, itbi, urban_planning, licensing, imagery, terrain, risk, environment, heritage, official_gazette.
- **PI** — faltam: lots, buildings, itbi, urban_planning, building_permits, licensing, habite_se, imagery, terrain, risk, environment, heritage, official_gazette.
- **BA** — faltam: lots, buildings, iptu, itbi, plan_director, zoning, building_permits, licensing, habite_se, terrain, risk, environment, official_gazette.
- **PA** — faltam: lots, buildings, zoning, urban_planning, building_permits, licensing, habite_se, imagery, terrain, risk, environment, heritage, official_gazette.
- **DF** — faltam: lots, iptu, itbi, zoning, urban_planning, licensing, imagery, terrain, risk, environment, heritage, official_gazette.

## Uso

```bash
python tools/discovery/analyze_coverage.py
```
