# Diário Nacional de Descoberta — 24/09/2026

## Resultado deste ciclo

A pesquisa confirmou que o Brasil não exige um único conector nacional. O padrão recorrente é:

1. **infraestrutura nacional** para identidade/endereço/ambiental;
2. **cadastro e legislação municipais** para o imóvel urbano;
3. **registro imobiliário** para direitos;
4. **fontes rurais federais** para limites e situação ambiental;
5. **dados derivados** para análise territorial.

### São Paulo

O GeoSampa é uma fonte estrutural. Há serviços WFS/WMS oficiais, e o WFS permite acesso vetorial a camadas municipais. O repositório oficial `geoinfo-smdu/download-lotes-geosampa` confirma o uso da camada `geoportal:lote_cidadao` e filtro por setor fiscal.

A SMUL também mantém o ecossistema Urbis, tecnicamente muito relevante para o LoteDiretor: MapLibre/deck.gl no frontend, PostGIS/GeoServer no geoprocessamento, CKAN para catálogo e pipelines orquestrados. Deve ser estudado como referência de arquitetura e conectores, observando as licenças de cada componente.

### Recife

Recife é hoje um dos melhores municípios para testar a arquitetura nacional porque reúne no portal oficial:
- IPTU em série histórica;
- ITBI em série histórica;
- dados urbanísticos;
- zoneamento/Plano Diretor;
- ArcGIS FeatureServer;
- licenciamento e instrumentos urbanísticos.

Isso permite testar em uma única cidade: identidade cadastral, tributação, transação, geometria e legislação.

### Belo Horizonte

Fontes oficiais permitem trabalhar:
- Plano Diretor Lei 11.181/2019;
- BHMAP/GeoSiurbe;
- legislação urbanística histórica;
- ITBI aberto;
- dados cadastrais/urbanísticos e licenciamento.

É um bom caso para testar histórico normativo.

### Porto Alegre

O portal de dados abertos publica ITBI por ano. Em 14/07/2026 a prefeitura sancionou novo Plano Diretor Urbano Sustentável e nova LUOS. Isso cria um caso ideal para validar mudança de vigência: documentos e mapas antigos não podem ser apresentados como regra atual.

### Fortaleza

O portal oficial de dados abertos possui cadastro fiscal relativo ao IPTU, áreas edificadas por uso, outorga onerosa, macrozoneamento, zonas especiais e outras camadas da SEUMA.

O portal do Plano Diretor já disponibiliza documentos e KMZ associados à Lei Complementar 450/2025. Fortaleza deve entrar no primeiro grupo de capitais monitoradas.

### Rio de Janeiro

Plano Diretor confirmado pela Lei Complementar 270/2024. O próximo ciclo deve aprofundar Data.Rio para localizar cadastro imobiliário, IPTU/ITBI, lote, edificações, licenciamento e camadas urbanísticas com endpoints diretamente ingeríveis.

### Curitiba

Plano Diretor Lei 14.771/2015, zoneamento Lei 15.511/2019 e revisão em andamento em 2026. O ecossistema do IPPUC será catalogado para downloads GIS, legislação e séries históricas.

### Vitória

PDU Lei 9.271/2018 com conjunto amplo de anexos. A documentação de aprovação edilícia é útil para modelar o fluxo de matrícula, IPTU, planta e levantamento georreferenciado.

### Goiânia

Plano Diretor LC 349/2022 confirmado. Serviços de ITBI mostram que inscrição municipal, matrícula e documentos da operação são identificadores/documentos importantes no fluxo real.

### Campinas

Plano Diretor LC 189/2018 e disciplina de uso/ocupação por LC 208/2018. O portal municipal de metadados oferece camadas SHP sem login. O recadastramento por aerofotogrametria de 2026 é relevante para atualização de área construída.

### São Luís

Plano Diretor Lei 7.122/2023. O portal mantém versões históricas, incluindo 2006 e 1992. Excelente caso para testar temporalidade jurídica.

## Fontes federais priorizadas

- Receita Federal: SINTER/CIB;
- IBGE: CNEFE e malhas;
- INCRA: SIGEF/SNCR;
- SICAR: CAR;
- ANA: hidrografia/outorgas;
- INPE: PRODES/DETER/TerraClass/imagens;
- FUNAI: terras indígenas e WMS/WFS;
- MMA/CNUC/ICMBio: unidades de conservação e outras restrições;
- ANM: processos minerários;
- IBAMA: embargos e demais bases abertas;
- IPHAN: patrimônio cultural e arqueologia;
- INDE: catálogo federado de serviços OGC.

## Próximos alvos de descoberta

1. Completar as 27 capitais com:
   - lei vigente do Plano Diretor;
   - lei de uso/ocupação/zoneamento;
   - portal GIS;
   - cadastro imobiliário/IPTU;
   - ITBI/transações;
   - licenciamento;
   - ortofoto/aerofoto;
   - risco/ambiental/patrimônio.

2. Descobrir automaticamente catálogos CKAN, ArcGIS REST e GeoServer municipais.

3. Criar registry de leis com vigência temporal e hashes dos PDFs/anexos.

4. Expandir para cidades médias, evitando arquitetura desenhada apenas para capitais.

5. Construir monitor de mudança: novos arquivos, alteração de endpoint, nova lei, revisão de Plano Diretor e mudança de esquema.


## Fiscal, ITBI e licenciamento — aprofundamento

### São Paulo

A legislação municipal determina disponibilização para consulta e download dos dados do cadastro imobiliário fiscal do IPTU via GeoSampa, em dados abertos e sob licença livre (Decreto 56.701/2015 com redação do Decreto 56.932/2016). A aplicação deve, porém, respeitar a orientação posterior da PGM sobre anonimização/inibição de dados pessoais à luz da LGPD.

Há evidências documentais e históricas de bases de ITBI vinculáveis por SQL, com natureza e valor da transação, proporção transmitida, VVR/base de cálculo e, em bases divulgadas em períodos anteriores, cartório/matrícula e atributos cadastrais. O endpoint oficial atual de download em massa de ITBI ainda precisa ser confirmado antes de promovê-lo a fonte ingerível automática.

### Recife

O IPTU 2026 é uma fonte excepcionalmente rica e licenciada sob ODbL. O dicionário inclui: número do contribuinte, CPF/CNPJ mascarado, endereço, fração ideal, área do terreno, área construída, área ocupada, valores unitários, ano da construção, pavimentos, uso, padrão, obsolescência, valor total estimado, IPTU, tipo construtivo e latitude/longitude.

O ITBI possui série 2015–2026+, também sob ODbL, com transações e características dos imóveis. O licenciamento urbanístico é atualizado diariamente e a outorga onerosa contém geolocalização, empreendimento, alvará e valores.

### Fortaleza

O portal de dados abertos da SEFIN expõe IPTU e ITBI em CSV. O ITBI é descrito como relação de transações imobiliárias com geolocalização, características dos imóveis e informações das operações. O portal também publica áreas edificadas por uso, trechos de logradouro e outros dados cadastrais.

### Porto Alegre

O portal publica IPTU em CSV de 2013 a 2026 e ITBI de 2020 a 2026, ambos sob Creative Commons Attribution. O IPTU 2026 tinha atualização registrada em 08/09/2026. Há ainda base de imunidades/benefícios fiscais.

### Belo Horizonte

Os relatórios mensais de ITBI incluem endereço, bairro, ano da construção, área de terreno, área construída adquirida, fração ideal, padrão de acabamento, tipo construtivo, ocupação, valor declarado, base de cálculo, zona de uso e data de quitação. O recurso consultado informa 'Nenhuma Licença Fornecida'; por isso foi classificado como LICENSE_REVIEW_REQUIRED e não como redistribuível automaticamente.

## Regra adicional de produto

Uma licença aberta de uma base fiscal não autoriza transformar identificadores de contribuintes em um mecanismo de busca de pessoas. A ingestão será property-centric: atributos do imóvel e transações ligadas ao imóvel, com minimização/segregação de campos pessoais quando presentes.


## Infraestrutura escondida, diretórios públicos e segunda onda municipal

### Diretórios e séries históricas

A pesquisa confirmou que mecanismos de busca tradicionais indexam mal diretórios de transferência. Por isso o projeto passou a manter `data/source-registry/public-directories.json` e um modo `directory` no harvester que enumera metadados sem baixar automaticamente os arquivos.

Fontes-mãe confirmadas:

- **IBGE GeoFTP**: malhas, setores censitários, bases cartográficas contínuas, ortomosaicos, geodésia e versões históricas. O próprio índice informa que os arquivos são públicos. Foram observadas BC250 2015, 2017, 2023 e 2025; a versão 2025 é distribuída em GeoPackage, PostGIS e shapefiles.
- **repositorio.dados.gov.br**: diretórios públicos do Governo Federal com séries históricas, Data Packages, arquivos removidos da navegação principal e dados de obras/patrimônio.
- **INPE/CPTEC**: servidor de transferência público para chuva, clima, nowcasting, oceano e modelos.
- **ANM/SIGMINE**: diretórios abertos de processos minerários, Brasil/UF e outros recursos.

A regra é guardar primeiro nome, caminho, data de modificação, tamanho, metadados, licença e lineage. Payloads grandes só entram no data lake depois da revisão.

### Gov360 — Imóveis da União

O `datapackage.json` oficial confirmou que `imoveis-da-uniao.csv` é explicitamente uma tabela de imóveis de uso especial da União administrados pela SPU, e não apenas um agregado genérico de patrimônio.

Na extração de maio/2026:
- 56.803 linhas;
- 19 campos;
- SHA-256 publicado;
- tipo de imóvel;
- tipo de destinação;
- regime de utilização;
- endereço;
- município/UF;
- área total;
- área construída;
- valor do imóvel;
- valor de aluguel.

O próprio pacote declara que as informações podem ser baixadas e utilizadas como dados abertos. Há snapshots históricos mensais, úteis para temporalidade.

### INCRA GeoNode

O portal de desenvolvedores do INCRA documenta WMS, WFS, WCS, CSW, OpenSearch, OAI-PMH e WMTS. Isso permite descobrir recursos/metadados programaticamente antes do download. Autenticação exigida por serviços específicos continua sendo respeitada sem bypass.

### Belo Horizonte — IDE-BHGEO/BHMap

A PBH confirma oficialmente WFS/WMS da IDE-BHGEO e acesso a dados pelo WFS. O BHMap tinha mais de 330 camadas em maio de 2026.

Camadas relevantes observadas no catálogo incluem:
- `LOTE_CTM`;
- `SQLV_LOTE_CTM`;
- `ENDERECO_POR_LOTE_CTM`;
- `EDIFICACAO`;
- tipologia de uso/ocupação;
- parâmetros da Lei 11.181/2019;
- redes de água/esgoto/energia;
- lote aprovado.

O endpoint oficial, não o diretório de terceiros que levou à descoberta, foi registrado como fonte.

### Santos

A página oficial de mapas urbanos é um dos melhores exemplos de distribuição municipal:

- lotes 2022, 2023, 2024 e 2026 em SHP/DXF;
- quadras;
- Plano Diretor LC 1.181/2022;
- alterações de perímetro pela LC 1.314/2025;
- LUOS insular LC 1.187/2022, alterada em 2025;
- zoneamento em SHP/GPKG;
- hierarquia viária;
- PEUC;
- uso do solo;
- risco/inundação;
- sítios arqueológicos.

Cada geometria deve guardar sua lei e data de referência.

### São José dos Campos

GeoSanja:
- portal público;
- WMS/WFS/WCS;
- metadados;
- exportações geoespaciais;
- busca por endereço/coordenada/inscrição imobiliária;
- camadas de zoneamento e Plano Diretor;
- imagens/ortofotos;
- comparação temporal.

O município instituiu CTM e, pelo Decreto 20.316/2026, aderiu ao SINTER. É um excelente caso para testar reconciliação CTM municipal → SINTER/CIB.

### Blumenau

O WFS oficial documenta diretamente:
- lotes;
- edificações;
- condomínios;
- loteamentos aprovados;
- drenagem;
- risco de deslizamento/enchente.

Há ainda FeatureServer público de lotes e endereços para a aplicação “Consulta para Construir”. É um caso de alto valor para a ficha predial.

### Santo André

O SIGA é a plataforma oficial municipal baseada em tecnologias livres e GeoServer. Setores, quadras e lotes fiscais foram abertos ao público em 2023, com download documentado. A própria prefeitura ressalva que a geometria fiscal não substitui levantamento topográfico/cartorial.

### Osasco

O OzMundi Cidadão abriu acesso visitante em maio de 2026. A prefeitura e o FAQ oficial afirmam que o sistema permite consultas e download; existe GeoNetwork próprio.

O sistema cita cadastros, certidão de uso do solo, loteamentos e matrículas. Como essas últimas podem envolver dados registrais/pessoais, qualquer conector deve aplicar bloqueio de campos e revisão LGPD antes de materialização pública.

### Balneário Camboriú

O GIS municipal em acesso público permite:
- lote;
- lista de unidades;
- itens cadastrais de edificação;
- área construída;
- valor venal total;
- valor venal do terreno;
- valor venal predial;
- consulta de viabilidade urbanística.

É fonte de consulta de alto valor, mas permanece `PUBLIC_QUERY_ONLY` até revisão explícita dos termos de reutilização.

### Jundiaí

GeoJundiaí combina:
- lotes;
- loteamentos;
- condomínios;
- áreas públicas;
- Plano Diretor/zoneamento;
- PGV;
- cartografia histórica;
- ortofotos 2012 e 2019;
- imagem IGC 2023/24.

O Cadastro Fiscal Imobiliário é explicitamente restrito a funcionários, portanto não há tentativa de bypass. A busca pública por matrícula/cartório também exige revisão antes de qualquer ingestão.

### Sorocaba

A SEPLAN fornece downloads ZIP de dados geoespaciais e explicita que as camadas são informativas, sem valor de documento oficial. Cada arquivo deve ser vinculado à respectiva norma e data.

### Controle de qualidade

O registry já possui `tools/discovery/validate_registry.py`.

A validação estrutural realizada após esta rodada confirmou:
- IDs únicos;
- classes de acesso válidas;
- códigos IBGE municipais com sete dígitos;
- URLs HTTP(S) estruturalmente válidas;
- campos mínimos de autoridade, escopo, domínio, tipo e status.

A escala já exige validação automática antes de cada merge.


## Operadores avançados de busca e ecossistema cartorial

### Decisão

Operadores como `site:`, `filetype:`, `intitle:`, `inurl:`, `intext:`, busca exata, OR e exclusões são oficialmente incorporados ao processo de descoberta, mas somente para localizar conteúdo público/oficial e documentação técnica.

A biblioteca de consultas está em:
- `data/source-registry/search-playbook.json`;
- `tools/discovery/generate_search_queries.py`;
- `docs/ADVANCED_PUBLIC_SOURCE_DISCOVERY.md`.

A pesquisa não procura credenciais, secrets, backups privados, dumps, painéis administrativos, documentos pessoais expostos acidentalmente ou rotas para contornar autenticação.

### Descobertas por dorks seguros

#### SINTER

A Receita Federal mantém documentação oficial da API SINTER/CADURB e Swagger em ambiente oficial. A documentação confirma:
- HTTP/HTTPS + JSON;
- versionamento `/v1/`;
- Bearer token obtido por Client ID/Client Secret;
- operações de inclusão, alteração, desativação e consulta;
- Swagger oficial;
- até 25 unidades em certas operações de escrita.

O registry foi atualizado para distinguir consulta pública de API autenticada.

#### Portal Brasileiro de Dados Abertos

O `dados.gov.br` mantém Swagger/OAS 3.1 e API REST oficial para listar/detalhar conjuntos de dados, organizações, temas, tags e reúsos. Esse endpoint passa a ser fonte-mãe para descoberta automática nacional.

#### ONR / RI Digital

Documentação pública localizada:
- especificação de Web Service para Visualização de Matrícula;
- Manual de Integração de Cartórios;
- exemplos de integração;
- documentação de Certidão Digital;
- Swagger público de serviço autenticado de atualização de matrículas.

Esses materiais revelam contratos técnicos, mas não tornam matrículas open data. Operações autenticadas não serão testadas sem autorização.

#### SERP / Meu Registro

O Provimento CNJ 229/2026 consolida o ecossistema SERP/Meu Registro e a interoperabilidade entre:
- ONSERP;
- ONR;
- ON-RCPN;
- ON-RTDPJ;
- serventias vinculadas.

A Receita Federal também informa que a integração das serventias ao SINTER está em construção conjunta com RFB, CNJ, ONR, CNB, municípios, Incra e MGI.

#### Justiça Aberta

O painel público do CNJ fornece cadastro institucional, produtividade e arrecadação de serventias, com atualização diária e exportação CSV/XLSX. Deve ser nossa fonte oficial para diretório de cartórios/CNS.

#### CENSEC

A Busca CEP é serviço pago e a consulta pública é deliberadamente limitada. A documentação técnica pública também descreve API para transmissão de cargas CEP, CESDI, RCTO e CTP, mas o uso operacional é reservado a atores autorizados.

Isso é valioso arquiteturalmente porque a CTP explicita o conceito de Comunicação de Transações às Prefeituras, mas não será tratada como API pública.

### São Bento do Sul

Operadores avançados revelaram serviço ArcGIS municipal `integracao/Cadastro_Imobiliario` com:
- Lotes;
- Edificações;
- Zoneamentos;
- Testadas;
- ITBI;
- Informações de unidade/terreno;
- Endereços;
- cadastro imobiliário.

O mesmo serviço lista uma tabela `Proprietarios` e campos potencialmente pessoais/sensíveis em tabelas relacionadas.

Decisão: fonte registrada com status `VERIFIED_SENSITIVE_TABLES_BLOCKED`. Camadas de lote/edificação poderão ser avaliadas; `Proprietarios` e dados pessoais ficam bloqueados independentemente de o endpoint ser tecnicamente consultável.

### Vitória

Foi identificado ArcGIS oficial da Prefeitura de Vitória com:
- `MapaBaseImobiliario`;
- `DominioFundiario`;
- `ImoveisCentro`;
- imagens;
- pasta `Opendata`.

Será enumerado serviço a serviço e cada licença/campo receberá classificação própria.

### Poços de Caldas

A Prefeitura mantém API REST oficial de dados abertos com JSON, CSV/XML, filtros, paginação e token temporário de visitante. O portal documenta geração legítima de token e playground.

A Câmara mantém acervo urbanístico de alto valor:
- diagnóstico histórico;
- dezenas de mapas em ZIP;
- DWG hidrogeológico;
- leis de Plano Diretor;
- LC 225/2022 com mapas;
- SIAVE com situação, vínculos e anexos de normas urbanísticas.

### Regra reforçada

**Indexado no Google/Bing ≠ autorizado para ingestão.**

Para o LoteDiretor, um endpoint só sai de `DISCOVERY` quando:
1. autoridade é confirmada;
2. finalidade/licença/termos são avaliados;
3. schema é inspecionado;
4. campos pessoais são filtrados;
5. ingestão/materialização é explicitamente aprovada.
