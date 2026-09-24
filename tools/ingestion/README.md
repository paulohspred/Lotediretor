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
- connector/source ID;
- autoridade;
- classe de acesso;
- licença;
- status de verificação da fonte.

## Uso

```bash
python tools/ingestion/snapshot.py gov360-imoveis-uniao
python tools/ingestion/snapshot.py rio-iptu
python tools/ingestion/snapshot.py rio-itbi
python tools/ingestion/snapshot.py blumenau-wfs
python tools/ingestion/snapshot.py bhgeo-wfs
python tools/ingestion/snapshot.py recife-ckan
python tools/ingestion/snapshot.py ibge-geoftp-index

# São Paulo
python tools/ingestion/snapshot.py sp-geosampa-wfs
python tools/ingestion/snapshot.py sp-geosampa-wms
python tools/ingestion/snapshot.py sp-geosampa-lidar-catalog
python tools/ingestion/snapshot.py sp-itbi-index
python tools/ingestion/snapshot.py sp-pgv-2026-law
```

O script é somente leitura. Ele não:

- autentica em sistemas restritos;
- contorna CAPTCHA;
- chama POST/PUT/DELETE;
- aceita URL com credencial embutida;
- segue redirect para IP privado, loopback, link-local ou reservado;
- baixa respostas acima do limite configurado;
- baixa automaticamente todos os arquivos de um diretório;
- materializa feições cuja licença ainda não foi aprovada.

O limite padrão de resposta é 50 MiB e pode ser reduzido com `--max-bytes`.

`metadata_first` significa que primeiro congelamos contrato/schema/metadados.
A materialização de registros/feições é uma etapa posterior e separada.

## Política de licença

O manifesto herda `authority`, `access_class`, `license` e
`verification_status` de `data/source-registry/bootstrap.json`.
Alcançabilidade técnica nunca substitui a revisão de licença/termos.

Para GeoSampa, a PMSP publica CC BY-SA 4.0 para dados geoespaciais produzidos
pelos seus próprios órgãos. Camadas de produtores externos continuam exigindo
revisão individual.
