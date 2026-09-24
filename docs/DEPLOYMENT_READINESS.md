# Deployment Readiness — ZoLa / LoteDiretor

**Data:** 24/09/2026

## Situação atual

- **169** fontes-mãe catalogadas.
- **50** municípios com pelo menos uma fonte municipal.
- **27/27 UFs** possuem ao menos alguma fonte catalogada no ecossistema.
- **18 cidades / 10 UFs** estão classificadas como prontas para um primeiro piloto ZoLa.
- **12 cidades** estão perto de entrar, faltando uma camada, adapter, licença ou revisão de campos.

## Cidades prontas para o primeiro piloto

1. **São Paulo/SP** — GeoSampa WFS/WMS + cadastro fiscal/IPTU + PDE/LPUOS.
2. **Santos/SP** — lotes SHP/DXF + zoneamento SHP/GPKG + Plano Diretor e histórico legal.
3. **São José dos Campos/SP** — GeoSanja + CTM/SINTER + zoneamento/Plano Diretor.
4. **Jundiaí/SP** — GeoJundiaí com lotes, zoneamento, PGV e ortofotos.
5. **Recife/PE** — lotes/ArcGIS + IPTU/ITBI CKAN + Plano Diretor + licenciamento.
6. **Rio de Janeiro/RJ** — parcelas/imóveis territoriais + IPTU/ITBI CC BY 4.0 + GeoPAL + planejamento.
7. **Niterói/RJ** — quadra/lote + Plano Diretor + serviços urbanísticos; aplicar field allowlist.
8. **Belo Horizonte/MG** — IDE-BHGEO WFS/WMS com lote CTM, edificação e parâmetros urbanísticos.
9. **Juiz de Fora/MG** — SISURB com lotes, edificações, Plano Diretor, risco e projetos aprovados.
10. **Goiânia/GO** — Mapa Tributário com unidade territorial + edifícios/PGV + Plano Diretor.
11. **João Pessoa/PB** — Atlas Filipeia com lotes SHP/CSV + zoneamento/PD 2024 + aerofotos.
12. **Pinhais/PR** — Mapa Cadastral/ITBI + Plano Diretor 2022 + edificações e ortofotos.
13. **Londrina/PR** — ArcGIS municipal com cadastro, zoneamento, Plano Diretor e imagens.
14. **Joinville/SC** — SIMGeo/ArcGIS com lotes fiscais, cadastro e planejamento urbano.
15. **Blumenau/SC** — WFS oficial com lotes, edificações, condomínios e consulta para construir.
16. **Florianópolis/SC** — GeoFloripa/GeoServer + CTM/cartografia oficial + zoneamento.
17. **Campo Grande/MS** — SIMGEO/CTM ArcGIS público + Plano Diretor/zoneamento.
18. **Vitória/ES** — ArcGIS municipal com mapa imobiliário + PDU/zoneamento.

## Próxima fila

1. **Porto Alegre/RS** — confirmar/normalizar parcel geometry no conector principal.
2. **Fortaleza/CE** — fiscal e PD fortes; confirmar camada vetorial de lote para seleção ZoLa.
3. **Manaus/AM** — ArcGIS forte, mas acesso é misto e parcela pública precisa ser isolada.
4. **Caxias do Sul/RS** — cadastro territorial forte; completar zoneamento/lei no adapter.
5. **Curitiba/PR** — GeoCuritiba + zoneamento prontos; completar atributos prediais/fiscais do piloto.
6. **Campinas/SP** — camadas SHP/metadados; consolidar lote + atributos de ficha.
7. **Santo André/SP** — lotes fiscais públicos; completar zoneamento/ficha normalizada.
8. **Osasco/SP** — OzMundi público; revisar campos registrais/LGPD e endpoints.
9. **Praia Grande/SP** — GeoServer público; enumerar camada vetorial de lote e licença.
10. **Porto Velho/RO** — GeoServer confirmado; enumerar/validar lotes, zoneamento e atributos.
11. **Rio Branco/AC** — cadastro/lotes excelentes; completar zoneamento/Plano Diretor vetorial.
12. **Belém/PA** — cadastro/serviços e PD existem; falta parcel dataset vetorial reutilizável confirmado.

## Decisão arquitetural

Não configurar ZoLa diretamente com 18 formatos municipais diferentes.

O desenho deve ser:

```
Prefeitura / Estado / União
        ↓
Connector
        ↓
Raw snapshot + Evidence
        ↓
Normalizer
        ↓
PostgreSQL / PostGIS
        ↓
LoteDiretor API
        ↓
ZoLa / futuro frontend MapLibre
```

O frontend vê sempre os mesmos contratos:
- parcel;
- building;
- address;
- zoning;
- urban rules;
- fiscal attributes;
- transactions;
- source/evidence.

## Primeiro deploy recomendado

Fase 1:
- São Paulo;
- Recife;
- Rio de Janeiro;
- Belo Horizonte;
- João Pessoa.

Essas cinco cidades testam padrões de fonte muito diferentes e suficientes para validar a arquitetura nacional.

Fase 2:
- Santos;
- São José dos Campos;
- Jundiaí;
- Goiânia;
- Pinhais;
- Londrina;
- Joinville;
- Blumenau;
- Florianópolis;
- Campo Grande;
- Vitória;
- Juiz de Fora;
- Niterói.

Não esperar as 5.571 cidades para colocar o produto no ar.
