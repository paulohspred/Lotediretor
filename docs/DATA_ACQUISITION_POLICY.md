# Política de Aquisição e Raspagem de Dados

**Versão:** 0.1  
**Data:** 24/09/2026

O LoteDiretor deve coletar agressivamente **metadados e dados legalmente reutilizáveis**, mas não deve contornar controles de acesso, violar termos de serviço ou transformar dados pessoais em um índice público.

## 1. O que podemos automatizar

Prioridade para interfaces oficiais e documentadas:

- WFS/WMS/WMTS e OGC API Features;
- ArcGIS REST MapServer/FeatureServer;
- CKAN API;
- GeoNetwork/CSW;
- STAC/COG;
- downloads oficiais CSV/GeoJSON/GPKG/SHP/KML/KMZ/ZIP/PDF;
- APIs governamentais;
- Diários Oficiais e legislação pública;
- páginas oficiais com anexos;
- GitHub/repositórios oficiais com licença compatível;
- sitemaps e catálogos públicos;
- datasets de dados abertos com licença verificável.

A descoberta pode ser ampla. A ingestão permanente só acontece depois de registrar licença, autoridade, cobertura, frequência e classificação de acesso.

## 2. O que não devemos fazer

- burlar CAPTCHA, login, autenticação gov.br, paywall ou controle de acesso;
- usar credenciais de terceiros;
- explorar endpoints privados ou não autorizados;
- ignorar bloqueios técnicos deliberados;
- raspagem massiva de dados pessoais apenas porque aparecem em consultas pontuais;
- republicar documentos pagos/restritos como se fossem open data;
- armazenar conteúdo cuja licença permita apenas visualização;
- inferir proprietário a partir de indícios e apresentar como fato.

## 3. Google Maps / Street View

Google pode ser usado como **integração de experiência do usuário**, respeitando APIs e termos oficiais.

Não usar Google como fonte de ingestão nacional para:

- copiar tiles;
- fazer download em massa de Street View;
- indexar ou cachear imagens;
- extrair uma base própria de edifícios/ruas a partir de imagens Google;
- rastrear manual/automaticamente contornos para criar um dataset derivado;
- armazenar resultados além das exceções previstas pelos termos aplicáveis.

Para dados persistentes priorizar: fontes governamentais, IBGE, INPE, Mapillary/licenças compatíveis, OpenStreetMap/Overture, Copernicus e outros datasets explicitamente reutilizáveis.

## 4. Dados pessoais e titularidade

Nome de proprietário, CPF, CNPJ, endereço pessoal, matrícula e direitos reais exigem tratamento separado.

Mesmo quando uma certidão puder ser solicitada por qualquer pessoa, isso não transforma os dados pessoais nela contidos em uma base aberta para indexação massiva.

O produto deve suportar:
- obtenção oficial sob demanda;
- documento fornecido pelo usuário;
- extração estruturada privada;
- controle de acesso;
- logs de auditoria;
- finalidade e retenção;
- exclusão quando aplicável.

## 5. Snapshot e proveniência

Para fontes reutilizáveis, cada coleta deve gerar:
- URL/endpoint;
- timestamp;
- cabeçalhos relevantes;
- tamanho;
- SHA-256;
- licença/termos conhecidos;
- versão do parser;
- contagem de registros;
- CRS;
- schema detectado;
- status de qualidade.

Nunca sobrescrever silenciosamente uma captura anterior.

## 6. Frequência

A frequência deve seguir a fonte, não uma agenda arbitrária:

- cadastro fiscal diário/semanal, se a origem atualizar assim;
- IPTU/ITBI anual/mensal conforme publicação;
- zoneamento quando houver alteração legal;
- Diário Oficial diariamente;
- dados ambientais conforme ciclo oficial;
- catálogos de fonte periodicamente para detectar novos recursos.

## 7. Regra de ouro

**Descobrir tudo não significa copiar tudo.**

O LoteDiretor deve saber que uma informação existe, onde obtê-la e sob quais condições, mesmo quando não puder armazená-la ou exibi-la publicamente.
