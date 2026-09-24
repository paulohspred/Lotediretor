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
