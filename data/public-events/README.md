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

Usar o novo ambiente de API pública:
`https://api-publica.obrasgov.gestao.gov.br`.

O ambiente antigo não é alvo de novos conectores. A integração real/paginada é
implementada na Fase H.

## PNCP

Consultas públicas GET podem ser usadas. Serviços de manutenção
(inserção/retificação/exclusão) ficam fora do LoteDiretor e não devem usar
credenciais.

## Validação

```bash
python tools/discovery/validate_public_event_resolver.py
```
