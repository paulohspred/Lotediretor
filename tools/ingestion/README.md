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
