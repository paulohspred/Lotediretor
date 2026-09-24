# Ecossistema cartorial e registral

O LoteDiretor deve integrar **serviços oficiais**, não construir um espelho informal dos cartórios.

## Princípio

Cadastro territorial, registro imobiliário, notas, registro civil, RTDPJ e protesto são sistemas diferentes.

Um imóvel público no mapa pode ter:
- CIB/SINTER;
- inscrição municipal;
- lote/edificação;
- matrícula em Registro de Imóveis;
- escrituras/procurações em Tabelionato de Notas;
- documentos em RTDPJ;
- partes com registros civis;
- protestos relacionados a uma pessoa/empresa.

Essas fontes não devem ser achatadas em uma única tabela.

## Descoberta segura

É válido pesquisar documentação pública com operadores como:

```
site:ridigital.org.br filetype:pdf ("web service" OR API OR integração) matrícula
site:onr.org.br ("documentação técnica" OR API) SREI
site:cnj.jus.br serventias extrajudiciais CSV CNS
site:notariado.org.br CENSEC API escritura procuração
```

Não é válido usar busca avançada para procurar:
- dumps;
- senhas/tokens;
- painéis internos;
- backups de cartórios;
- documentos pessoais publicados por engano;
- índices massivos de CPF/proprietário fora dos serviços oficiais.

## Caminho de integração

### Diretório

CNJ/Justiça Aberta fornece o mapa institucional de serventias e CNS.

### Registro de Imóveis

ONR/RI Digital é a fonte oficial para certidão, visualização de matrícula e demais serviços registrais eletrônicos.

A documentação técnica pública do ONR é útil para compreender interoperabilidade. O fato de um Swagger ou manual estar público não torna as operações de dados abertas.

### Notas

CENSEC contém índices nacionais de atos notariais. Consultas e APIs têm regras próprias, pagamento/credenciamento e restrições de publicidade.

### SERP

O Provimento CNJ 229/2026 consolidou o ecossistema SERP e a marca Meu Registro, envolvendo ONSERP, ONR, ON-RCPN e ON-RTDPJ.

### SINTER

A Receita Federal informa que a integração de cartórios ao SINTER está sendo estruturada em conjunto com CNJ, ONR, CNB, municípios, Incra e MGI.

Isso reforça a decisão arquitetural de guardar identificadores externos separados e preparar reconciliação:
`CIB ↔ inscrição municipal ↔ lote ↔ matrícula/CNS`.

## Resultado esperado

Para o usuário, a ficha do imóvel deve dizer:

- qual cartório/circunscrição é relevante, quando identificável;
- qual matrícula foi fornecida ou obtida oficialmente;
- data/tipo da certidão;
- direitos/restrições extraídos;
- origem exata de cada afirmação;
- status: oficial, documento privado, inferido ou pendente.

Nome de proprietário e demais dados pessoais permanecem em domínio restrito.
