# Infraestrutura, Processos, Patrimônio e Contexto Financeiro

Esta camada amplia o LoteDiretor para além de cadastro/zoneamento.

## Energia elétrica

A ANEEL publica a **BDGD — Base de Dados Geográfica da Distribuidora**, parte do SIG-R, sob ODbL. A base representa ativos reais das distribuidoras em Geodatabase e possui atualização anual.

O relatório pode indicar:
- distribuidora;
- área de concessão;
- ativos elétricos próximos;
- classe/tensão quando disponível;
- transformadores/subestações próximos;
- geração distribuída e contexto de qualidade/tarifa.

**Importante:** um transformador ou rede próxima não significa disponibilidade de potência para um novo empreendimento. Quando isso for decisivo, o resultado deve ser `CONNECTION_REQUEST_REQUIRED` até manifestação da concessionária.

## Gás canalizado

Estratégia:
1. identificar concessionária/regulador;
2. usar mapa público como contexto;
3. identificar rede aparente próxima;
4. quando houver obra/escavação, direcionar ao cadastro técnico oficial;
5. nunca usar um mapa indicativo como planta executiva de rede subterrânea.

Comgás, Gasmig, Copergás e PBGás já têm canais oficiais de mapa. Naturgy exige solicitação do cadastro da rede antes de escavação.

## Água e esgoto

SINISA fornece prestador, cobertura e indicadores nacionais.

Para informação predial/viária:
- procurar GIS/dados abertos da companhia;
- GIS municipal;
- regulador;
- solicitação de viabilidade/ligação quando necessário.

Estados possíveis:
- prestador conhecido;
- município coberto;
- rede pública conhecida no entorno;
- ligação confirmada;
- viabilidade pendente.

## Telecomunicações

Anatel fornece dados abertos para:
- estações licenciadas;
- prestadoras;
- banda larga fixa;
- móvel;
- backhaul;
- tecnologias;
- medições de campos eletromagnéticos.

O relatório pode mostrar antenas/estações próximas e contexto de oferta, mas não prometer fibra em uma unidade apenas com dados municipais.

## Obras públicas

ObrasGov será usado para localizar:
- obra pública próxima;
- geometria;
- situação;
- execução física;
- execução financeira;
- valor;
- órgão responsável.

PNCP complementa:
- edital;
- contrato;
- ata;
- fornecedor;
- documentos da contratação.

Isso pode revelar futuras intervenções viárias, drenagem, escolas, unidades de saúde, urbanização e outras obras capazes de alterar o entorno do imóvel.

## Processos administrativos

Fontes:
- SEI Pesquisa Pública;
- portais municipais/estaduais de processo;
- licenciamento ambiental;
- processos urbanísticos;
- ANEEL/ANP/ANM quando relacionados;
- DataJud para processo judicial público **já identificado por número/tribunal**.

O LoteDiretor não deve construir busca nacional de processos por proprietário.

## CNO

O Cadastro Nacional de Obras não é público.

Só responsável, corresponsável ou contratante pode consultar via e-CAC. Portanto:
- não raspar;
- não tentar descobrir CNO de terceiros;
- aceitar documento/CNO fornecido pelo cliente;
- manter em domínio privado;
- relacionar à obra/imóvel com evidência.

## Patrimônio

O relatório deve verificar três esferas:
- IPHAN;
- órgão estadual;
- órgão municipal.

E diferenciar:
- imóvel tombado;
- processo de tombamento;
- área envoltória;
- patrimônio ambiental/paisagístico;
- sítio arqueológico;
- área de interesse arqueológico.

A incidência sempre deve levar à resolução/ato e ao órgão que precisa aprovar intervenção.

## Custos

SINAPI permite adicionar ao estudo:
- custo de referência de insumos;
- composições;
- custo por UF/mês;
- composição paramétrica de viabilidade.

O número deve ser identificado como **referência**, não orçamento executivo.

## Mercado e financiamento

Banco Central:
- mais de 4.000 séries mensais do mercado imobiliário;
- crédito;
- fontes de recursos;
- imóveis financiados;
- recortes estaduais.

Serve para contextualização macro/estadual. Não substitui avaliação de mercado do lote.

## Status de infraestrutura

Todo serviço deve usar um destes estados:

- `UNKNOWN`
- `PROVIDER_IDENTIFIED`
- `CONCESSION_AREA`
- `NETWORK_OBSERVED_NEARBY`
- `SERVICE_REPORTED_IN_AREA`
- `TECHNICAL_AVAILABILITY_CONFIRMED`
- `CONNECTION_REQUEST_REQUIRED`
- `TECHNICAL_DRAWING_REQUIRED`
- `NOT_AVAILABLE`
- `RESTRICTED_INFORMATION`

Essa distinção evita uma das falhas mais perigosas em relatórios imobiliários: afirmar que um serviço está disponível apenas porque uma linha aparece próxima no mapa.
