# LoteDiretor Platform API

Scaffold do **Data Plane** definido no Blueprint Final v2.0.

- NestJS modular monolith.
- Fastify adapter.
- Mercurius GraphQL.
- REST e GraphQL no mesmo serviço.
- Python permanece como engine/worker de ETL/geoprocessamento durante a migração.
- `POST /parcel/resolve` já tem contrato de transição e delega aos resolvedores Python validados.
- `GET /healthz` e `Query.platformStatus` servem como primeiros contract checks.

## Runtime

Node >= 20.9.0. O host legado ainda está em Node 18, portanto este serviço não deve substituir a API atual até o runtime/container novo e os testes de contrato estarem prontos.

## Próximos módulos

`iam`, `core`, `geo`, `legal`, `planning`, `cadastre`, `registry`, `market`, `property360`, `rural`, `condo`, `municipality`, `analysis`, `report`.
