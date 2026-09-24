# Public territorial events

A Fase D normaliza sinais oficiais que podem antecipar mudanças no entorno de
um imóvel:

- projetos/obras públicas;
- editais e contratações;
- contratos;
- licenças e aprovações;
- movimentos de processo;
- atos de Diário Oficial.

O contrato está em `event.schema.json` e a seleção de fontes em
`source-resolver.json`.

## Regra de correlação

Prioridade:

```text
geometria oficial
→ identificador público do imóvel
→ endereço oficial
→ proximidade espacial
→ referência documental
→ texto
```

Texto sozinho nunca confirma que um evento pertence a um imóvel.

Não descobrir processos por proprietário, CPF, CNPJ de pessoa, requerente ou
outro identificador pessoal. Número de processo pode ser mantido quando o
processo é público e sua relação com o imóvel/projeto é legítima.

## ObrasGov

Ambiente atual:

```text
https://api-publica.obrasgov.gestao.gov.br/obras
```

Contrato de recursos:

```text
data/public-events/obrasgov-api.json
```

Cliente read-only:

```bash
python tools/ingestion/obrasgov.py projects \
  --filter uf_principal=SP \
  --page-size 50 \
  --pages 1
```

Para geometrias por município:

```bash
python tools/ingestion/obrasgov.py geometries \
  --filter cod_ibge=3550308 \
  --page-size 50 \
  --pages 1
```

O conector usa somente o ambiente atual de 2026. O ambiente antigo não é alvo
de novos conectores.

## PNCP

Base pública de consulta:

```text
https://pncp.gov.br/api/consulta
```

Contrato:

```text
data/public-events/pncp-api.json
```

Contratações publicadas em município/período:

```bash
python tools/ingestion/pncp.py publications \
  --start 20260901 \
  --end 20260924 \
  --modality 6 \
  --municipality 3550308 \
  --page-size 50 \
  --pages 1
```

Contratos publicados em período:

```bash
python tools/ingestion/pncp.py contracts \
  --start 20260901 \
  --end 20260924 \
  --page-size 50 \
  --pages 1
```

Serviços de manutenção/inserção/retificação/exclusão ficam fora do LoteDiretor.
Nenhuma credencial de manutenção do PNCP é usada.

## Limites operacionais

Os clientes em `tools/ingestion/`:

- usam apenas HTTPS/GET;
- aceitam somente hosts oficiais allowlisted;
- recusam redirect para host não permitido;
- limitam tamanho de resposta;
- limitam quantidade de páginas;
- não fazem crawl nacional implícito;
- não contornam CAPTCHA/autenticação.

ObrasGov limita página a 200 registros e execução a 20 páginas por chamada.
PNCP usa no máximo 50 registros por página, 20 páginas por chamada e janela de
até 365 dias.

## Normalização

ObrasGov:

```bash
python tools/normalization/public_events.py \
  obrasgov-projects \
  data/snapshots/obrasgov-projects/<timestamp>/page-00001.json \
  --out /tmp/obrasgov-events.ndjson
```

PNCP:

```bash
python tools/normalization/public_events.py \
  pncp-publications \
  data/snapshots/pncp-publications/<timestamp>/page-00001.json \
  --out /tmp/pncp-events.ndjson
```

Validar os eventos:

```bash
python tools/normalization/validate_public_events.py /tmp/pncp-events.ndjson
```

Validar o resolver de fontes:

```bash
python tools/discovery/validate_public_event_resolver.py
```

## Semântica do PNCP

O filtro municipal do PNCP descreve a localidade da unidade administrativa da
contratação. Ele não prova que a obra/serviço está fisicamente naquele
município nem, muito menos, em um lote específico.

Por isso, eventos PNCP permanecem `UNRESOLVED` até surgir uma relação oficial
adicional: geometria, endereço de execução, identificador de projeto, processo
ou documento que permita a correlação.

## Primeira onda municipal

`source-resolver.json` mapeia São Paulo, Recife, Rio de Janeiro, Belo Horizonte
e João Pessoa para:

- licenciamento;
- Diário Oficial;
- processo administrativo;
- ObrasGov;
- PNCP.

Os portais municipais continuam obedecendo à classe de acesso original:
`OPEN_REUSABLE`, `PUBLIC_QUERY_ONLY` ou `AUTHENTICATED_PUBLIC`.
