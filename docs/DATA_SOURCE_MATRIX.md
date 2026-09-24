# LoteDiretor — Matriz Inicial de Fontes de Dados

**Versão:** 0.1  
**Data:** 24/09/2026

Esta matriz transforma a pesquisa inicial em um catálogo operacional. A classificação de acesso deve ser revisada antes de cada integração de produção.

| Domínio | Fonte/autoridade | Cobertura | O que pode fornecer | Acesso pretendido | Tratamento no LoteDiretor |
|---|---|---|---|---|---|
| Identidade imobiliária | Receita Federal — SINTER/CIB | Nacional em expansão | CIB, inscrição municipal, endereço, áreas, dados construtivos e outros campos conforme cadastro de origem | Público parcial + integração credenciada | Usar CIB como identificador externo preferencial; não como PK interna única |
| Endereços | IBGE — CNEFE | Nacional | Endereços georreferenciados urbanos e rurais | Público | Geocodificação, busca e reconciliação de endereço |
| Limites administrativos | IBGE | Nacional | UF, município, distrito e outras divisões | Público | Referência territorial nacional |
| Cadastro urbano | Prefeituras | Municipal | lote, inscrição, área, uso, construção, testada, valor venal, zoneamento etc. | Varia por município | Conector municipal padronizado + snapshot |
| Titular cadastral | SINTER/prefeituras | Varia | titular e tipo de titularidade podem existir na origem | Restrito/não público por padrão | Domínio protegido; nunca publicar por inferência |
| Registro jurídico | RI Digital / Registro de Imóveis | Nacional, serviços variam por cartório | matrícula, certidões, ônus, propriedade, documentos arquivados | Sob demanda/pago/autenticado | Documento oficial + extração estruturada + validação/hash |
| Pesquisa por pessoa | RI Digital — Pesquisa Nacional de Bens | Cobertura parcial por Estado/cartório | matrículas associadas a CPF/CNPJ | Sob demanda | Apenas descoberta; não afirmar propriedade atual sem qualificação/certidão |
| Transações | DOI / Receita Federal | Nacional | operações imobiliárias e partes | Sigilo/restrito | Não presumir API pública |
| Transações municipais | ITBI / dados abertos locais | Municipal | transações, valores e atributos conforme portal local | Varia; alguns municípios publicam open data | Conector específico com revisão jurídica/licença |
| Plano Diretor | Prefeitura/Câmara/Diário Oficial | Municipal | lei, anexos, macrozoneamento, instrumentos | Público | Texto + anexos + vigência + geometria + citações |
| Zoneamento/LPUOS | Prefeitura/Câmara | Municipal | zonas, usos, índices, parâmetros, exceções | Público em graus variados | Motor de regras versionado; não reduzir lei a simples interseção espacial |
| Licenciamento edilício | Prefeituras | Municipal | alvará, processo, habite-se, projeto aprovado, metadados | Varia | Separar metadados públicos de peças restritas |
| Planta/projeto | Prefeitura/cartório/usuário | Municipal/documental | plantas e peças gráficas | Frequentemente sob demanda/restrito | Armazenamento privado; OCR/extração; nunca presumir disponibilidade nacional |
| Fachada | Usuário / Mapillary / integração externa | Global/local | imagem de rua | Varia | Preferir usuário/Mapillary/licença compatível; Google apenas visualização permitida |
| Imagem orbital | INPE / Copernicus / outras fontes licenciadas | Nacional/global | séries temporais e orto/satélite | Público/licenciado | Snapshot/COG/STAC com atribuição |
| Edificações | Prefeitura / OSM / Overture / Open Buildings | Municipal/nacional/global | footprint, presença, contexto | Varia por fonte | Oficial primeiro; fallback claramente identificado |
| Altura estimada | Google Open Buildings 2.5D Temporal | Brasil incluído | presença, contagem e altura derivada 2016–2023 | Open data | Contexto/estimativa; nunca substituir dado cadastral ou levantamento |
| Topografia | INPE Topodata / Copernicus DEM / IBGE / municipal | Nacional + local | elevação e derivados | Público/licenciado | Fallback nacional para screening; priorizar MDT/LiDAR local |
| Cadastro rural | INCRA/SNCR/CIB Rural | Nacional | identificação rural | Público/restrito conforme serviço | Reconciliação rural |
| Limite rural certificado | INCRA — SIGEF | Nacional | limites georreferenciados certificados | Consulta autenticada em parte | Evidência fundiária; não confundir com titularidade registral |
| Ambiental rural | SICAR/CAR | Nacional | CAR e camadas ambientais declaradas | Consulta/dados públicos conforme serviço | Evidência declaratória; não tratar CAR como prova dominial |
| Recursos hídricos | ANA | Nacional/federal | hidrografia, outorgas, monitoramento | Dados abertos | Restrições/contexto hídrico |
| Mineração | ANM — SIGMINE | Nacional | processos minerários e áreas | Público | Interseção com imóvel + situação do processo |
| Embargos | IBAMA | Nacional | embargos ambientais | Público | Interseção/alerta com evidência |
| Risco | SGB + estados/municípios | Parcial/nacional por tema | suscetibilidade, setores de risco | Público | Cobertura explícita; ausência não significa ausência de risco |
| Patrimônio | IPHAN + estados/municípios | Nacional/local | bens protegidos e áreas de influência | Público/variável | Camadas de restrição e consulta |
| Documento do cliente | Usuário | Qualquer | matrícula, IPTU, escritura, planta, levantamento, laudo | Privado | Tenant privado, criptografia, auditoria e extração versionada |

## Estados de acesso

Todo conector deve declarar um dos estados:

- **OPEN_REUSABLE** — ingestão e redistribuição permitidas pela licença.
- **PUBLIC_QUERY_ONLY** — consulta permitida, mas cache/redistribuição precisam ser limitados.
- **AUTHENTICATED_PUBLIC** — acesso possível ao cidadão autenticado, sem implicar direito de replicação.
- **RESTRICTED_PERSONAL** — contém dados pessoais/restritos.
- **PAID_ON_DEMAND** — documento/consulta oficial mediante pedido e/ou emolumento.
- **USER_PRIVATE** — fornecido pelo usuário e mantido privado.
- **DERIVED** — produzido pelo LoteDiretor a partir de entradas identificadas.

## Regra de integração

Nenhuma fonte entra em produção sem:

1. autoridade responsável;
2. URL/documentação oficial;
3. cobertura geográfica;
4. termos/licença;
5. classificação de acesso;
6. esquema de campos;
7. frequência de atualização;
8. estratégia de versionamento;
9. testes de qualidade;
10. política para dados pessoais;
11. comportamento quando a fonte estiver indisponível;
12. registro de proveniência e data de captura.

## Prioridade de fontes

A ordem de preferência deve ser:

**fonte oficial local/nacional atual > documento oficial sob demanda > fonte aberta consolidada > fonte comunitária/licenciada > inferência do LoteDiretor**.

Fontes inferiores podem preencher contexto, mas não devem sobrescrever silenciosamente uma evidência oficial divergente.
