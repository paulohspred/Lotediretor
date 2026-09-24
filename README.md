# LoteDiretor Brasil

Plataforma nacional de inteligência territorial e imobiliária para pesquisa, análise e documentação técnica de imóveis urbanos e rurais no Brasil.

O projeto parte do [ZoLa — New York City Zoning & Land Use Map](https://github.com/NYCPlanning/labs-zola) como **baseline funcional de experiência cartográfica**, não como arquitetura nacional definitiva.

## Estado atual

- Baseline ZoLa oficial importado de `NYCPlanning/labs-zola@a31db6e6d50c81d77facca50367e08c1bdf09f6a`.
- Token Mapbox embutido no upstream removido; a configuração usa `MAPBOX_ACCESS_TOKEN`.
- Baseline preservado na branch `baseline/zola-upstream-2026-08-20`.
- Pesquisa inicial de dados imobiliários, cadastro, registro, legislação e referências internacionais em:
  [docs/RESEARCH_PROPERTY_DATA_BRAZIL_WORLD.md](docs/RESEARCH_PROPERTY_DATA_BRAZIL_WORLD.md).

## Objetivo do produto

Para cada imóvel analisado, o LoteDiretor deve reunir o máximo de informação **legalmente acessível, tecnicamente verificável e rastreável**, incluindo, quando disponível:

- identificação cadastral e territorial;
- CIB/SINTER e identificadores municipais;
- endereço e geometrias oficiais;
- cadastro/IPTU;
- matrícula, certidões e direitos reais em fluxos apropriados;
- legislação urbanística, Plano Diretor, zoneamento e parâmetros;
- edificações, licenças, habite-se e documentos;
- imagens, ortofotos e contexto construído;
- topografia, drenagem, riscos e restrições;
- dados ambientais e rurais;
- histórico e evidências de fontes;
- documentos fornecidos pelo usuário;
- análises derivadas com método e versão explícitos.

O sistema não deve preencher lacunas com suposições. Cada conclusão relevante precisa distinguir dado oficial, dado restrito, documento fornecido, dado inferido e cálculo do LoteDiretor.

## Direção arquitetural

O ZoLa é mantido como referência para mapa, busca, seleção de lote, camadas, ficha do imóvel, comparação e impressão.

Para escala nacional, a direção técnica é desacoplar progressivamente:

- frontend geoespacial moderno;
- API orientada por contratos;
- PostgreSQL/PostGIS;
- catálogo nacional de fontes e conectores;
- pipeline ETL/ELT versionado;
- armazenamento de objetos para snapshots e documentos;
- modelo de identidade imobiliária que não confunda lote, IPTU, matrícula, unidade autônoma, edificação e imóvel rural;
- separação rigorosa entre dados públicos, pessoais/restritos e documentos privados.

A pesquisa e as decisões iniciais estão documentadas em [docs/RESEARCH_PROPERTY_DATA_BRAZIL_WORLD.md](docs/RESEARCH_PROPERTY_DATA_BRAZIL_WORLD.md).

## Licença e origem

O código do baseline ZoLa foi publicado pelo NYC Department of City Planning. O arquivo [LICENSE](LICENSE) importado do upstream contém dedicação ao domínio público/CC0 1.0.

LoteDiretor não é afiliado nem endossado pelo NYC Department of City Planning.
