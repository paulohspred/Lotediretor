# Three-level heritage resolver

A Fase E resolve patrimônio cultural em três níveis para as cinco cidades da
primeira onda:

```text
IPHAN
→ órgão estadual
→ órgão municipal
```

Arquivo principal:

```text
data/heritage/first-wave-resolver.json
```

## Estados separados

O LoteDiretor não reduz patrimônio a um booleano. O resolver distingue:

- `PROTECTED_ASSET`;
- `PENDING_PROTECTION`;
- `SURROUNDING_AREA`;
- `PROTECTED_AREA`;
- `ARCHAEOLOGY`;
- `LEGAL_ACT`;
- `APPROVAL_AUTHORITY`.

Um processo de tombamento não vira tombamento definitivo. Uma APAC/ZEPH/área
envoltória não vira automaticamente tombamento individual.

## Regra de incidência

A evidência preferida é:

1. geometria oficial;
2. ato/resolução/decreto;
3. identificador oficial do bem/processo;
4. consulta documental do órgão competente.

Quando houver área envoltória oficial, ela deve ser usada em vez de inventar um
buffer genérico.

Uma geometria derivada só é aceitável quando a regra jurídica for
determinística, os insumos forem oficiais e o resultado for marcado
explicitamente como `DERIVED`.

## Particularidades

### São Paulo

GeoSampa consolida bens/áreas protegidas por CONPRESP, CONDEPHAAT e IPHAN,
incluindo processos de tombamento, áreas envoltórias e arqueologia. O portal
estadual CONDEPHAAT continua sendo a autoridade jurídica estadual.

### Recife

IEP municipal e ZEPH são categorias diferentes. Fundarpe mantém bens tombados
e processos estaduais. A publicação do edital estadual pode iniciar proteção
provisória antes da homologação final.

### Rio de Janeiro

APAC é área de proteção do ambiente cultural e não equivale a tombamento
individual. O IRPH publica atos/decretos por APAC. O INEPAC permanece a
autoridade estadual.

### Belo Horizonte

Os datasets municipais de patrimônio são publicados sob CC BY e versionados
mensalmente. `Bem Cultural Imóvel` mantém graus distintos de proteção,
incluindo tombamento e processo aberto.

### João Pessoa

Filipeia publica cartografia de patrimônio IPHAN/IPHAEP. O IPHAEP mantém as
regras estaduais de centros históricos e aprovação de intervenção. A licença
dos artefatos vetoriais patrimoniais ainda precisa ser confirmada.

## Validação

```bash
python tools/discovery/validate_heritage_resolver.py
```

A validação é offline e verifica:

- as cinco cidades obrigatórias;
- os três níveis em cada cidade;
- todos os `source_id`;
- capacidades conhecidas;
- regras mínimas de proteção municipal/estadual.
