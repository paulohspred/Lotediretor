# Descoberta avançada de fontes públicas

## Objetivo

Operadores de busca avançada são úteis para localizar **fontes oficiais já publicadas**, principalmente quando um portal não liga diretamente para seus serviços técnicos, catálogos ou arquivos históricos.

O objetivo não é encontrar “vazamentos”. É encontrar melhor:

- ArcGIS REST/FeatureServer/MapServer;
- GeoServer WFS/WMS/WCS;
- GeoNetwork/GeoNode;
- Swagger/OpenAPI;
- CKAN e APIs de dados abertos;
- CSV/JSON/XML/GPKG/SHP/KMZ/DWG/PDF;
- anexos de legislação;
- Diários Oficiais;
- acervos e versões históricas;
- documentação técnica de cartórios/SERP;
- diretórios públicos de transferência.

A biblioteca estruturada está em `data/source-registry/search-playbook.json`.

## Regra de segurança

Uma URL pública ou indexada **não é, por si só, autorização de reutilização**.

Se uma busca revelar uma área que aparente conter:
- proprietário nominal;
- CPF/CNPJ;
- documentos de identidade;
- credenciais;
- token;
- backups internos;
- banco de dados;
- dados médicos/benefícios;
- arquivos registrais privados;
- painel administrativo;

o conteúdo não é usado como dataset. Não tentamos ampliar acesso, fazer enumeração massiva ou contornar autenticação.

## Estratégia

### 1. Primeiro a autoridade

Sempre restringir, quando possível, a:
- domínio oficial `.gov.br`;
- Câmara/Assembleia/Senado;
- CNJ;
- Receita Federal;
- ONR/RI Digital;
- Operadores Nacionais reconhecidos;
- autarquia ou empresa pública responsável.

### 2. Depois a tecnologia

Buscar padrões recorrentes:
- `rest/services`;
- `FeatureServer`;
- `MapServer`;
- `geoserver`;
- `GetCapabilities`;
- `geonetwork`;
- `swagger`;
- `openapi`;
- `api`;
- `dados-abertos`.

### 3. Depois o domínio imobiliário

Termos:
- lote;
- edificação;
- quadra;
- inscrição imobiliária;
- cadastro fiscal;
- IPTU;
- ITBI;
- PGV;
- zoneamento;
- Plano Diretor;
- LUOS;
- alvará;
- habite-se;
- projeto aprovado;
- ortofoto;
- LiDAR;
- matrícula;
- certidão.

### 4. Histórico

Buscar também:
- acervo;
- histórico;
- versão anterior;
- revogada;
- alterada;
- arquivos retirados;
- 2010, 2015, 2020 etc.

O objetivo é construir séries temporais, não apenas a versão corrente.

## Cartórios

A descoberta de cartórios é diferente de GIS.

Fontes principais:
- CNJ / Justiça Aberta: diretório de serventias e CNS;
- SERP / Meu Registro;
- ONR / RI Digital;
- ON-RCPN / Registro Civil;
- ON-RTDPJ;
- CENSEC / CNB-CF;
- CENPROT / IEPTB.

Documentação técnica pública pode ser catalogada. APIs autenticadas ou serviços pagos não são tratados como open data.

Uma especificação pública de web service do ONR, por exemplo, é útil para compreender o contrato de interoperabilidade de matrícula, mas não autoriza consultar matrículas fora dos canais oficiais.

## Pipeline

```
SEARCH_CANDIDATE
    ↓
OFFICIAL_DOMAIN_CONFIRMED
    ↓
TERMS_LICENSE_REVIEWED
    ↓
SCHEMA_INSPECTED
    ↓
PRIVACY_FILTERED
    ↓
SOURCE_REGISTRY_APPROVED
    ↓
SNAPSHOT / CONNECTOR
```

Se qualquer etapa falhar, a fonte permanece apenas como descoberta.
