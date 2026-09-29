# Barueri Coverage — 2026-09-28

Estado: **address-first**. Nesta auditoria não foi verificada base oficial aberta de lotes com geometria cadastral reproduzível. Não ativar parcelSupported nem Martin para Barueri até existir materialização confiável.

| Tema | Fonte | Endpoint | Tipo | Cobertura | Status | Integrado? | Próximo passo | Limitação |
|---|---|---|---|---|---|---|---|---|
| Cadastro/IPTU | Cadastro imobiliário online | https://servicos.barueri.sp.gov.br/emissaocertidao/certidaocadastral.aspx | PUBLIC_QUERY_ONLY | Consulta cadastral individual | LIVE, CAPTCHA | False | Aguardar arquivo/export oficial ou fornecido pelo usuário | Sem bulk e sem geometria cadastral aberta verificada |
| Cadastro/IPTU | 2ª via IPTU | https://www.barueri.sp.gov.br/sistemas/2via/?tipo=1 | PUBLIC_QUERY_ONLY | Inscrição do imóvel / exercício atual | LIVE | False | Usar somente consulta manual/documental; materializar arquivo autorizado | Formulário, não dataset espacial |
| Valor venal | Certidão de Valor Venal | https://servicos.barueri.sp.gov.br/emissaocertidao/CertidaoVenal.aspx | PUBLIC_QUERY_ONLY | Inscrição + exercício | LIVE, CAPTCHA | False | Somente evidência documental fornecida/consultada legitimamente | CAPTCHA; sem bulk |
| Zoneamento | LC 565/2023 + PRC_COMPLETA_2023 | https://portal.barueri.sp.gov.br/cidadao/moradia/mapa-zoneamento | DOWNLOADABLE_DATASET | Município | Documento oficial vetorial; não GeoPDF | referência | Recuperar transformação espacial verificável antes de extrair polígonos | Proibido georreferenciar no olho |
| Licenciamento | Aprova Digital Barueri | https://barueri.aprova.com.br/ | AUTHENTICATED_PRIVATE | Alvarás, Habite-se, certidões, parcelamento e fiscalização | LIVE | False | Manter link/registro; integrar apenas fluxo autorizado autenticado | Conta/autenticação; não inferir licença por endereço |
| Processos urbanísticos | Consulta legada SPU | https://www.barueri.sp.gov.br/sistemas/processoEngenharia/ | PUBLIC_QUERY_ONLY | Protocolo + CPF/CNPJ | LIVE, CAPTCHA | False | Consulta manual quando houver protocolo/documento | CAPTCHA e identificadores pessoais |
| Meio ambiente | Indicadores ambientais municipais | https://portal.barueri.sp.gov.br/cidadao/secretaria-recursos-naturais-meio-ambiente/indicadores | PUBLIC_QUERY_ONLY | Água, esgoto, arborização, drenagem, licenciamento e outros | LIVE | contexto | Auditar datasets exportáveis por painel | Indicadores agregados não provam incidência/capacidade no lote |
| Meio ambiente | Relatórios de licenciamento e APP | https://portal.barueri.sp.gov.br/cidadao/secretaria-recursos-naturais-meio-ambiente/relatorio-licenciamento | PUBLIC_QUERY_ONLY | Publicações de licenças e vegetação/APP | LIVE | False | Indexar documentos somente com chaves documentais seguras | Não associar por texto/endereço isolado |
| Mobilidade | Plano de Mobilidade Urbana | https://portal.barueri.sp.gov.br/secretarias/mobilidade-urbana/plano-mobilidade- | DOWNLOADABLE_DATASET | Produtos, mapas e vetores KMZ | DOWNLOAD disponível | False | Baixar e auditar KMZ por camada/CRS/data | Plano de mobilidade não é cadastro parcelar |
| Lotes espaciais | Pesquisa em portais oficiais/ArcGIS/GeoServer | — | NOT_SUITABLE_FOR_PARCEL | Barueri | NÃO ENCONTRADO nesta auditoria | False | Usar materializador quando houver SHP/GPKG/GeoJSON/GDB/DXF/DWG/PDF transformável | Não inventar geometria cadastral |
| Contexto nacional | IBGE Censo 2022 / malhas | registry:br-ibge-censo2022-sector-mesh | DOWNLOADABLE_DATASET | Barueri e Brasil | já materializado nacionalmente | True | Manter como contexto, não como lote | Setor censitário não é parcela |
| Contexto rural | SICAR | registry:br-sicar-car | LIVE_WFS | SP / rural | já registrado | contexto | Usar apenas campos públicos não pessoais | CAR é declaratório e não prova domínio |
| Contexto rural | SIGEF público/privado | registry:br-incra-sigef | AUTHENTICATED_PRIVATE | Brasil | misto | contexto | Manter atos completos fora do conector público | Não inferir propriedade |
| Finanças/obras | SICONFI / TransfereGov / ObrasGov / PNCP | registry:br-siconfi-api; registry:br-transferegov-public-works; registry:br-obrasgov-api; registry:br-pncp-open-api | LIVE_API | Município/entes públicos | já registrados | contexto | Filtrar Barueri por código/CNPJ oficial quando necessário | Obra/contrato não deve ser ligado ao lote só por texto/endereço |
| Infraestrutura federal | DNIT SNV | registry:br-dnit-snv | LIVE_WFS | Brasil | já registrado | contexto | Usar distância/incidência geométrica com caveat | Proximidade não prova acesso/faixa de domínio |
| Risco geológico/hidrológico | Plano Municipal de Adaptação e Resiliência Climática 2025 | https://portal.barueri.sp.gov.br/arquivos/sites/sm/2025/Plano_de_Adaptacao_e_Resiliencia_Climatica_rev1.pdf | DOWNLOADABLE_DATASET | 248 setores com coordenadas UTM publicadas | MATERIALIZADO EM POSTGIS COMO PONTOS DE REFERÊNCIA | True | Obter banco georreferenciado original do Instituto Geológico para polígonos | Ponto publicado não representa a extensão do setor |
| Infraestrutura/gestão territorial | GeoPixel Cidades · WMS municipal | https://barueri.geopixel.com.br/geoserver-barueri/barueri/wms | LIVE_WMS | Eixos, dutos, obras, TIC Oeste e licenciamento | LIVE · allowlist validada; WFS desativado | True | Reavaliar cadastro quando houver acesso vetorial/metadados coerentes | WMS é visual; não usar para point-in-polygon; camadas com bbox incoerente rejeitadas |

## Regra de ativação do lote

ld_stage.barueri_lotes só pode ser publicado quando a origem tiver geometria verificável, CRS conhecido/recuperável e identificadores cadastrais documentados. PDF vetorial sem transformação espacial verificável permanece documento, não camada espacial.

## Classificação operacional

- Formulários com CAPTCHA: PUBLIC_QUERY_ONLY; não automatizar CAPTCHA.
- Aprova Digital: AUTHENTICATED_PRIVATE; não contornar autenticação.
- PRC 2023: DOWNLOADABLE_DATASET documental/vetorial, porém não apto a point-in-polygon enquanto a transformação espacial não for comprovada.
- KMZ do Plano de Mobilidade: DOWNLOADABLE_DATASET, sujeito a auditoria de camada/CRS/semântica.
