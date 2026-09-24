# Coverage Report — Source Registry

**Data:** 24/09/2026  
**Fontes-mãe:** 165  
**Municípios com ao menos uma fonte municipal identificada:** 48

Este relatório é calculado a partir de `data/source-registry/bootstrap.json`. Ele mede **presença de domínios**, não qualidade ou completude dos dados.

## Domínios-chave

`cadastre`, `lots`, `buildings`, `iptu`, `itbi`, `plan_director`, `zoning`, `urban_planning`, `building_permits`, `licensing`, `habite_se`, `imagery`, `terrain`, `risk`, `environment`, `heritage`, `official_gazette`

## UFs com maior lacuna operacional

| UF | Fontes | Municípios | Domínios-chave presentes | Faltantes |
|---|---:|---:|---:|---:|
| RR | 1 | 1 | 1/17 | 16 |
| TO | 1 | 0 | 1/17 | 16 |
| PI | 1 | 1 | 2/17 | 15 |
| RO | 1 | 1 | 2/17 | 15 |
| MT | 2 | 1 | 2/17 | 15 |
| AP | 1 | 1 | 3/17 | 14 |
| MS | 1 | 0 | 3/17 | 14 |
| AL | 2 | 1 | 3/17 | 14 |
| RN | 1 | 1 | 4/17 | 13 |
| BA | 3 | 1 | 4/17 | 13 |
| PA | 3 | 1 | 4/17 | 13 |
| DF | 2 | 0 | 5/17 | 12 |
| SE | 2 | 1 | 5/17 | 12 |
| GO | 4 | 1 | 5/17 | 12 |
| AC | 2 | 1 | 6/17 | 11 |

## Regra de prioridade

Uma UF/capital não é considerada operacionalmente coberta apenas por possuir Plano Diretor ou um portal cartográfico.

Prioridade de busca:
1. cadastro/lote/edificação;
2. IPTU/ITBI/PGV;
3. zoneamento/Plano Diretor com vigência;
4. licenciamento, alvará e habite-se;
5. imagem/ortofoto/topografia;
6. risco, ambiente e patrimônio;
7. Diário Oficial e histórico normativo.

## Uso

```bash
python tools/discovery/analyze_coverage.py
```

O resultado completo é gravado em `data/source-registry/coverage-report.json`.
