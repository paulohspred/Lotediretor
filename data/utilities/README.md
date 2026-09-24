# Utility provider resolver

O arquivo `data/utilities/municipality-provider-resolver.json` implementa a Fase C
da primeira onda L3:

```text
municipality
→ utility provider
→ service territory
→ technical datasets
```

Cobertura inicial:

- São Paulo/SP;
- Recife/PE;
- Rio de Janeiro/RJ;
- Belo Horizonte/MG;
- João Pessoa/PB.

Serviços modelados:

- distribuição de energia;
- gás;
- água/esgoto;
- telecom;
- drenagem;
- iluminação pública.

## Semântica de disponibilidade

O resolver separa quatro conceitos:

1. `PROVIDER_TERRITORY_ONLY`: confirma quem presta/regula o serviço;
2. `NETWORK_CONTEXT`: há infraestrutura ou indicador técnico no entorno;
3. `PARCEL_AVAILABILITY`: existe evidência oficial específica para o imóvel/endereço;
4. `SUBMUNICIPAL_REQUIRED`: município não basta para resolver o prestador.

Nunca converter automaticamente proximidade de rede em “serviço disponível”.

## Rio de Janeiro

Água/esgoto é deliberadamente submunicipal. A capital é dividida entre múltiplas
concessionárias; portanto o código IBGE `3304557` sozinho não resolve o prestador.
O próximo nível de implementação deve usar território oficial versionado
(polígono/bairro/endereço), com tratamento explícito de áreas parciais.

## Dados técnicos

A BDGD/ANEEL é o contexto técnico preferencial para ativos de distribuição elétrica.
Anatel fornece contexto regulatório/infraestrutural de telecom, não confirmação de
fibra/serviço em um lote. SINISA fornece contexto de saneamento/prestadores, não
substitui cadastro técnico de rede nem consulta de ligação.

Dados de unidade consumidora, titular, contrato ou pessoa ficam fora do resolver.

## Validação

```bash
python tools/discovery/validate_utility_resolver.py
```

O validador é offline e verifica:

- as cinco cidades obrigatórias;
- os seis serviços por cidade;
- referências a `source_id`;
- referências a datasets técnicos;
- consistência de território;
- preservação do caso submunicipal do Rio.
