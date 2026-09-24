# Database model — Phase G

O banco do LoteDiretor é um **modelo nacional normalizado**, não um espelho dos
formatos de cada prefeitura.

Primeira migration:

```text
database/migrations/001_initial_postgis.sql
```

Contrato/invariantes:

```text
database/schema-contract.json
```

## Fluxo

```text
fonte oficial
→ snapshot imutável + hash
→ normalized_record
→ tabela de domínio
→ interseção/reconciliação com subject
→ assertion + evidência/unknown
→ relatório/API pública
```

## Schemas

- `ld_catalog`: fontes, conectores, snapshots e registros normalizados;
- `ld_core`: identidade do imóvel e reconciliação;
- `ld_domain`: dados tipados de planejamento, fiscal, ITBI, licenças, risco,
  patrimônio, utilities, eventos, imagens e terreno;
- `ld_evidence`: afirmações por imóvel, lineage de derivados e lacunas;
- `ld_api`: somente fundação de read models públicos.

## Identidade

Não achatar:

- lote municipal;
- unidade fiscal/IPTU;
- edificação;
- unidade condominial;
- referência de matrícula;
- imóvel rural.

A relação entre eles é explícita em `subject_relation` e sempre possui
confiança/proveniência.

## Geometria

A geometria vetorial nacional canônica usa **SIRGAS 2000 / EPSG:4674**.

O CRS original permanece na proveniência/asset quando relevante. Cálculos em
metros/m² devem usar projeção adequada ou método geodésico; não calcular área
métrica diretamente em coordenadas angulares.

## Temporalidade

Snapshots são append-only. Dados jurídicos, fiscais, cadastrais e geográficos
podem ter:

- `valid_from`;
- `valid_to`;
- `observed_at`;
- `captured_at`.

Uma versão nova não deve apagar silenciosamente a anterior.

## Evidência

`ld_evidence.assertion` é a camada usada pelo relatório profissional.

Um fato pode ser:

- oficial;
- resultado de consulta oficial;
- vindo de documento do usuário;
- derivado;
- contexto indicativo;
- desconhecido.

Derivados precisam de método e lineage.

`ld_evidence.unknown` evita transformar ausência de informação em afirmação de
ausência.

## Privacidade

O schema público **não precisa e não deve depender** de nomes de proprietários,
CPF/CNPJ, requerentes ou conteúdo integral de certidões privadas.

Matrícula, certidões, ônus e documentos do usuário pertencem ao L4 e deverão
usar armazenamento/autorização privados em etapa posterior.

## Validação estática

```bash
python tools/discovery/validate_database_schema.py
```

Essa validação não substitui aplicar a migration em PostgreSQL/PostGIS numa
etapa de integração. Deploy de banco continua fora desta fase.
