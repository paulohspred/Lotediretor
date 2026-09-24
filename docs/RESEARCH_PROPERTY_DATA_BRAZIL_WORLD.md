# LoteDiretor — Pesquisa e Arquitetura Nacional de Dados Imobiliários

**Status:** pesquisa inicial v0.1  
**Data:** 24/09/2026  
**Baseline de referência:** ZoLa oficial `NYCPlanning/labs-zola@a31db6e6d50c81d77facca50367e08c1bdf09f6a`

## 1. Objetivo

O LoteDiretor não deve ser apenas um visualizador de zoneamento. O objetivo é formar um dossiê técnico, territorial, cadastral, registral, urbanístico, ambiental e construtivo de um imóvel, com rastreabilidade de fonte, data, versão, licença e nível de acesso.

O sistema deve tentar descobrir o máximo de informação legalmente disponível sobre um imóvel, sem confundir:

- lote cadastral municipal;
- unidade imobiliária tributária/IPTU;
- matrícula ou transcrição do Registro de Imóveis;
- unidade autônoma em condomínio;
- endereço;
- edificação;
- parcela ou imóvel rural;
- CAR;
- parcela georreferenciada/SIGEF;
- CIB;
- pessoa ou organização relacionada a direitos sobre o imóvel.

Essas entidades podem coincidir em alguns casos, mas não são semanticamente equivalentes.

## 2. Conclusão sobre o ZoLa

ZoLa é uma excelente referência de produto para:

- mapa como porta de entrada;
- seleção de lote;
- camadas temáticas;
- ficha contextual do lote;
- busca;
- comparação;
- impressão;
- deep links;
- interação entre mapa e dados urbanísticos.

ZoLa não deve ser tratado como arquitetura final nacional. O código atual é uma SPA Ember fortemente vinculada ao ecossistema e ao modelo de dados de Nova York, com dependências de Layers API, Carto e conceitos locais como BBL. Para 5.571 municípios, múltiplos regimes de cadastro, dados rurais, documentos registrais, informação pessoal restrita e fontes versionadas, será necessário um núcleo novo.

O próprio NYC Planning mantém um PoC moderno separado, usando React, MapLibre, deck.gl, TypeScript e uma API NestJS/PostGIS/OpenAPI, além de pipelines ETL separados. Esse desenho é uma referência técnica mais próxima da escala pretendida pelo LoteDiretor.

**Decisão proposta:** preservar ZoLa como baseline e referência funcional, mas construir o núcleo nacional em arquitetura desacoplada e migrar gradualmente a experiência do mapa.

## 3. Modelo conceitual do imóvel

Adotar conceitos compatíveis com ISO 19152 LADM, sem tentar implementar a norma literalmente.

### Entidades centrais

**Property Subject**  
Entidade de reconciliação interna. Representa o “imóvel analisado” pelo usuário, sem assumir que um único identificador oficial resolve toda a identidade.

**Spatial Unit**  
Geometria ou espaço legal/físico: lote, parcela, unidade autônoma, edificação, área rural, servidão, volume 3D.

**Identifier**  
CIB, inscrição municipal, SQL/BCI, matrícula + cartório, transcrição, CCIR/SNCR, SIGEF, CAR, CEP/endereço e identificadores municipais.

**Party**  
Pessoa física, pessoa jurídica, ente público ou outra parte relacionada a direitos. Dados pessoais devem ficar separados do domínio público.

**RRR — Right, Restriction, Responsibility**  
Direitos, ônus, servidões, usufrutos, hipotecas, indisponibilidades, restrições ambientais, tombamento, regras urbanísticas e obrigações.

**Building**  
Edificação física, com footprint, área construída, pavimentos, uso, idade estimada/declarada, licenças e documentos.

**Source / Snapshot / Evidence**  
Toda afirmação deve apontar para uma fonte e para uma captura/versionamento daquela fonte.

## 4. Regra fundamental de evidência

Nenhum campo técnico relevante deve existir apenas como “valor atual”.

Cada fato deve poder carregar, no mínimo:

- valor;
- unidade;
- fonte;
- autoridade;
- data de publicação;
- data de captura;
- validade temporal;
- método de obtenção;
- URL ou identificador documental;
- licença/termo de uso;
- classificação de acesso;
- nível de confiança;
- geometria associada, quando aplicável;
- hash do artefato de origem quando pudermos armazená-lo;
- aviso quando for inferido/calculado.

Exemplo: “área do lote = 450 m²” pode existir simultaneamente como área cadastral municipal, área geométrica calculada, área constante na matrícula e área de levantamento fornecido pelo usuário. O sistema não deve sobrescrever essas diferenças; deve explicá-las.

## 5. Classes de acesso

### A. Público e redistribuível
Dados oficiais ou abertos cuja licença permite ingestão, armazenamento e redistribuição.

Exemplos: limites administrativos, CNEFE divulgado pelo IBGE, muitas camadas municipais, imagens INPE conforme licença aplicável, dados ambientais abertos.

### B. Público para consulta, mas com restrição de redistribuição
Pode ser visualizado ou consultado, porém os termos podem impedir cache, cópia em massa ou redistribuição.

Exemplo importante: Google Street View. A política do Street View Static API geralmente proíbe pré-busca, indexação, armazenamento e cache do conteúdo, exceto identificadores específicos. Deve ser integração de visualização, não fonte para nosso banco de imagens.

### C. Pessoal/restrito
Titularidade, CPF e outras informações pessoais devem ficar em domínio protegido, com base legal, finalidade, minimização, auditoria e controle de acesso.

O SINTER informa expressamente que a consulta pública não apresenta titulares nem informações de ITBI. Dados cadastrais sigilosos/sensíveis do CIB são reservados ao titular autenticado.

### D. Adquirido sob demanda
Certidões, matrículas, documentos cartoriais ou documentos de prefeitura que exijam pedido, pagamento, identificação ou autorização.

Esses artefatos não devem ser tratados como open data apenas porque podem ser requeridos por terceiros.

### E. Fornecido pelo usuário
Matrícula, escritura, IPTU, planta, levantamento topográfico, projeto arquitetônico, laudo, foto, contrato, memorial, CAR, CCIR etc.

Devem ficar em armazenamento privado, com OCR/extração controlada e trilha de origem.

### F. Derivado pelo LoteDiretor
Interseções espaciais, cálculo de área, declividade, distância, envelope, risco preliminar, estimativa de altura, análise de imagens etc.

Todo resultado derivado deve declarar método, versão do algoritmo e entradas utilizadas.

## 6. Brasil — fontes nacionais prioritárias

### SINTER / CIB
É a principal mudança estrutural para o projeto. O CIB está sendo implantado como identificador nacional de imóveis urbanos e rurais.

Em 14/09/2026, a Receita Federal divulgava 29.459.440 CIBs ativos, sendo 20.455.076 urbanos e 9.004.364 rurais, com 2.065 municípios aderentes e 26 capitais/DF integrados.

O CIB deve ser tratado como chave externa nacional preferencial, mas não como única chave interna. A cobertura ainda é incompleta e a integração dos demais municípios entra no ciclo obrigatório de 2027.

### IBGE / CNEFE
Base nacional de endereços georreferenciados. Deve servir de backbone para geocodificação, busca e reconciliação endereço-coordenada.

O IBGE disponibiliza arquivos públicos por município/UF em CSV e GeoJSON. O CNEFE não é cadastro de propriedade nem de titularidade.

### Registro de Imóveis / RI Digital
A matrícula é a principal fonte jurídica dos direitos reais registrados. O sistema deve permitir:

1. identificar cartório e matrícula quando houver evidência;
2. solicitar/encaminhar consulta oficial quando possível;
3. receber certidão digital do usuário;
4. extrair partes, atos, direitos, restrições e descrições;
5. manter o documento e a extração em domínio restrito.

Não devemos construir uma lista pública nacional de proprietários a partir de raspagem massiva.

### DOI / transações
Cartórios enviam à Receita Federal a Declaração sobre Operações Imobiliárias para aquisições e alienações. A base contém matrícula, partes e dados da operação, mas grande parte do uso está sujeita a sigilo fiscal e regras específicas de compartilhamento.

Conclusão: DOI não deve ser presumida como API pública do LoteDiretor.

Alguns municípios publicam dados de ITBI em dados abertos, como Porto Alegre, e outros publicam apenas agregados. Conectores de transações serão municipais e terão política de campo por campo.

### Cadastro municipal / IPTU
É municipal e extremamente heterogêneo. Dependendo da cidade, podemos encontrar:

- inscrição imobiliária;
- lote;
- testada;
- área territorial;
- área construída;
- padrão construtivo;
- uso;
- ano da construção;
- valor venal;
- zoneamento;
- endereço;
- dados de licenciamento;
- edificações;
- eventualmente nome cadastral do contribuinte/proprietário, quando a legislação local publicar.

Disponibilidade pública local não implica que o LoteDiretor deva republicar indiscriminadamente dados pessoais.

### Licenciamento edilício
Projetos aprovados, plantas, alvarás, certificados de conclusão/habite-se e processos edilícios existem nas prefeituras, mas o acesso e a digitalização variam muito.

O produto deve separar:
- metadados do processo/alvará;
- peças gráficas públicas;
- peças acessíveis apenas ao proprietário/representante;
- documentos obtidos via LAI;
- documentos fornecidos pelo usuário.

Não existe hoje uma fonte nacional única de plantas de imóveis.

### Rural
O modo rural deve integrar progressivamente:

- CIB Rural / SNCR;
- SIGEF;
- CAR/SICAR;
- APP e Reserva Legal;
- terras indígenas;
- unidades de conservação;
- embargos e restrições ambientais;
- hidrografia/outorgas;
- uso e cobertura da terra;
- desmatamento e séries temporais;
- relevo;
- limites administrativos e fundiários disponíveis.

O SIGEF disponibiliza informações georreferenciadas de limites de imóveis rurais; a consulta pública atualmente exige autenticação gov.br prata/ouro. O SICAR oferece consulta pública e downloads de dados públicos.

## 7. Imagens e geometria de edificações

### Fachada/casa
Prioridade:
1. imagem fornecida pelo usuário;
2. imagem municipal/aerofotogramétrica oficialmente licenciada;
3. Mapillary, respeitando CC-BY-SA e termos aplicáveis;
4. Street View apenas incorporado/consultado de acordo com os termos, sem criar nosso próprio arquivo permanente de imagens Google.

### Satélite/aérea
INPE deve ser uma fonte nacional importante. O catálogo CBERS/Amazonia-1 permite cópia e redistribuição das imagens disponibilizadas, com atribuição à fonte conforme as condições publicadas.

### Footprint e contexto construído
Usar fonte oficial municipal quando disponível. Para cobertura nacional de fallback, avaliar Overture Maps/OpenStreetMap e derivados licenciados.

Overture documenta fontes brasileiras que incluem IBGE e Google Open Buildings, com licenças específicas por tema/fonte.

### Altura de edifícios
Não confundir altura observada/estimada com altura legal ou cadastral. Google Open Buildings 2.5D Temporal cobre Brasil com rasters anuais 2016–2023 de presença, contagem e altura de edifícios derivados de Sentinel-2. Pode servir para contexto/estimativa, nunca como certidão da altura real.

## 8. Plano Diretor e legislação urbanística

A maior dificuldade de escala nacional não é renderizar o mapa; é interpretar e versionar regras de 5.571 municípios e múltiplas autoridades estaduais/federais.

Cada regra deve ter:

- jurisdição;
- diploma legal;
- artigo/quadro/anexo;
- data de publicação;
- vigência;
- revogação/substituição;
- geometria territorial aplicável;
- parâmetros estruturados;
- texto original citado;
- método de interpretação;
- estado: oficial, extraído, revisado, calculado ou pendente.

O motor não deve afirmar automaticamente “pode construir X” apenas porque uma camada espacial interceptou um lote. Interseção espacial é evidência; conclusão jurídica exige regras e exceções.

## 9. Arquitetura técnica proposta

### Web
Direção alvo: React + TypeScript + MapLibre GL + deck.gl.

O ZoLa Ember fica como referência funcional e pode ser usado temporariamente para validar fluxos, mas não devemos aumentar o acoplamento nacional ao modelo Ember/Carto existente.

### API
API orientada por contratos OpenAPI, com módulos de:
- propriedades;
- identificadores;
- fontes;
- evidências;
- geometrias;
- legislação;
- documentos;
- partes/direitos restritos;
- relatórios;
- jobs de ingestão/materialização.

NestJS é uma opção coerente com o PoC atual do NYC Planning, mas não é requisito de domínio.

### Banco
PostgreSQL + PostGIS para entidades, geometrias, relações e metadados.

### Objetos
Storage compatível com S3 para snapshots, PDFs, imagens, arquivos GIS, relatórios e documentos privados.

### Tiles
MapLibre no cliente, com tiles vetoriais/raster servidos por infraestrutura própria. Martin é candidato forte para PostGIS/PMTiles/MBTiles/COG.

### Pipelines
ETL/ELT separado da API. Cada conector deve ser idempotente e versionado.

Tipos iniciais de conector:
- ArcGIS REST/FeatureServer;
- GeoServer WFS/WMS;
- OGC API Features;
- CKAN;
- CSV/GeoJSON/GPKG/SHP;
- download HTTP versionado;
- STAC/COG;
- HTML/PDF/diário oficial;
- APIs autenticadas;
- integração manual assistida quando não houver API.

## 10. Reconciliação de identidade

A pergunta “qual é este imóvel?” precisa de um motor próprio.

Entrada possível:
- clique no mapa;
- endereço;
- coordenada;
- CIB;
- inscrição IPTU;
- matrícula;
- CAR;
- SIGEF;
- CEP + número;
- documento enviado.

Saída:
- um Property Subject;
- candidatos encontrados;
- relações entre identificadores;
- geometrias potencialmente divergentes;
- evidências de vínculo;
- conflitos explicitados.

Não devemos unir automaticamente duas entidades apenas porque têm endereço parecido.

## 11. Privacidade e segurança

A arquitetura deve ter separação física/lógica entre:

**Dados públicos**  
Podem ser indexados e exibidos segundo licença.

**Dados pessoais/restritos**  
Criptografia, autenticação, autorização, trilha de auditoria, finalidade e retenção.

**Documentos do cliente**  
Tenant privado, controle de compartilhamento e exclusão.

**Segredos de integrações**  
Nunca no frontend ou no Git. O primeiro import já encontrou um token Mapbox embutido no upstream e ele foi removido durante a importação.

## 12. Referências internacionais

### ISO LADM
É a melhor referência conceitual para não misturar parcela, pessoa, direito, restrição, fonte e geometria em uma tabela única.

### Espanha — Catastro
Padrão útil: dados cadastrais e cartográficos amplamente consultáveis; dados pessoais protegidos separados.

### Nova Zelândia — LINZ
Padrão útil: parcelas e títulos como infraestrutura oficial; propriedade em massa requer licença específica de dados pessoais.

### Reino Unido — HM Land Registry
Padrão útil: geometrias e preço de transações disponibilizados como open data, enquanto serviços registrais detalhados continuam em camadas próprias.

### Países Baixos — BAG
Padrão especialmente relevante para o CIB: municípios são fontes oficiais de endereço/edificação e os dados são consolidados nacionalmente em uma infraestrutura central.

## 13. Estratégia de implementação

Antes de “converter o mapa para o Brasil”, construir contratos que provem três cenários diferentes:

1. **São Paulo/SP — metrópole com dados urbanos muito ricos.**
2. **Município médio com portal ArcGIS/GeoServer ou dados parciais.**
3. **Imóvel rural — fontes nacionais/federais predominantes.**

Se a arquitetura funcionar apenas em São Paulo, ela não é nacional.

## 14. Primeiros marcos recomendados

### Marco 0 — baseline
Concluído: ZoLa oficial importado e preservado em branch de baseline.

### Marco 1 — catálogo nacional de fontes
Criar Source Registry com autoridade, município/UF/país, cobertura, licença, formato, atualização, autenticação, disponibilidade e qualidade.

### Marco 2 — modelo de identidade imobiliária
Implementar Property Subject, Spatial Unit, Identifier, Building, Party/RRR restritos e Evidence.

### Marco 3 — geocodificação nacional
IBGE/CNEFE + limites oficiais + fallback licenciado.

### Marco 4 — primeiro cadastro urbano
Conector de São Paulo apenas para provar o contrato genérico, não para criar classes específicas de São Paulo no núcleo.

### Marco 5 — legislação versionada
Plano Diretor, zoneamento, parâmetros e anexos como dados versionados e citados.

### Marco 6 — documentos
Upload privado + extração estruturada de matrícula/IPTU/planta/documentos, preservando o original.

### Marco 7 — rural
SIGEF/CAR/ambiental/hidrologia/uso do solo.

### Marco 8 — frontend nacional
Migrar a experiência aprovada do ZoLa para o stack moderno.

## 15. Critério de qualidade do produto

A interface deve sempre responder quatro perguntas:

**O que sabemos?**  
Fatos e geometrias confirmados.

**De onde veio?**  
Fonte, documento e data.

**O que foi calculado?**  
Método e entradas.

**O que ainda não sabemos?**  
Ausência de fonte, acesso restrito, conflito ou dado pendente.

A ausência de informação nunca deve ser preenchida por uma suposição silenciosa.

## 16. Fontes oficiais e técnicas consultadas nesta pesquisa inicial

- Receita Federal — SINTER/CIB, cobertura cadastral, consulta pública, integração municipal e regras de titularidade.
- IBGE — CNEFE e downloads de endereços georreferenciados.
- Receita Federal — DOI e regras de sigilo fiscal.
- Registro de Imóveis / RI Digital — serviços registrais eletrônicos.
- INCRA — SIGEF.
- SICAR — Consulta Pública do CAR.
- ANA — dados abertos e outorgas de recursos hídricos.
- INPE — catálogo CBERS/Amazonia-1 e política de redistribuição publicada.
- ISO 19152-1:2024 e ISO 19152-2:2025 — LADM.
- HM Land Registry — Price Paid Data e dados públicos.
- LINZ New Zealand — cadastro, títulos e licença específica para ownership em massa.
- Kadaster Netherlands — BAG.
- Google Maps Platform — política de Street View e cache.
- Overture Maps — atribuições e fontes.
- Google Research — Open Buildings 2.5D Temporal.
- NYC Planning — labs-zola, ae-zoning-map-poc, ae-zoning-api e ae-data-flow.

---

Este documento é uma base de arquitetura e pesquisa, não parecer jurídico. Regras de acesso, proteção de dados e licenciamento precisam ser verificadas por fonte e por integração antes de produção.
