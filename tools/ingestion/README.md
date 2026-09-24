# Read-only source snapshots

Este diretório define conectores iniciais para fontes já aprovadas.

## Objetivo

Antes de ETL, transformação ou carga PostGIS, salvar um snapshot reproduzível contendo:

- URL solicitada e URL final;
- timestamp UTC;
- status HTTP;
- Content-Type/Length;
- ETag/Last-Modified quando disponíveis;
- SHA-256;
- resposta bruta;
- connector/source ID.

## Uso

```bash
python tools/ingestion/snapshot.py gov360-imoveis-uniao
python tools/ingestion/snapshot.py rio-iptu
python tools/ingestion/snapshot.py rio-itbi
python tools/ingestion/snapshot.py blumenau-wfs
python tools/ingestion/snapshot.py bhgeo-wfs
python tools/ingestion/snapshot.py recife-ckan
python tools/ingestion/snapshot.py ibge-geoftp-index
```

O script é somente leitura. Ele não:
- autentica em sistemas restritos;
- contorna CAPTCHA;
- chama POST/PUT/DELETE;
- segue endpoints privados;
- baixa automaticamente todos os arquivos de um diretório;
- materializa feições cuja licença ainda não foi aprovada.

`metadata_first` significa que primeiro congelamos contrato/schema/metadados. A materialização de registros/feições é uma etapa posterior e separada.

## Validação do dossiê normalizado

O contrato machine-readable do dossiê está em
`data/property-dossier/dossier-contract.schema.json`.

Além do JSON Schema, o validador em stdlib verifica invariantes de proveniência
que não devem depender apenas do frontend:

- fato `AVAILABLE` precisa carregar valor e evidência;
- fato `DERIVED` precisa registrar método e fatos de origem;
- `NO_EVIDENCE` nunca pode carregar valor;
- dados `QUERY_ONLY`, `RESTRICTED` ou dependentes de documento do usuário não
  podem ser públicos por padrão;
- referências a geometrias e fatos upstream precisam resolver.

Exemplo:

```bash
python tools/ingestion/validate_dossier.py \
  data/property-dossier/example-minimal.json
```

O exemplo é propositalmente fictício e serve apenas para validar o contrato.
