# Dossiê Profissional do Imóvel

O objetivo do LoteDiretor não é apenas exibir um lote no mapa. É responder, para cada imóvel:

> **O que um arquiteto, engenheiro, corretor, avaliador, advogado, incorporador, perito ou investidor precisa saber antes de projetar, comprar, vender, financiar, regularizar ou desenvolver este imóvel?**

## Níveis de completude

- **L0 — Descoberta:** sabemos que uma fonte existe.
- **L1 — Mapa:** lote/localização + zoneamento.
- **L2 — Urbanístico:** L1 + cadastro do terreno/edificação + parâmetros legais.
- **L3 — Profissional:** L2 + IPTU/PGV, ITBI/mercado, licenciamento, risco/ambiente, infraestrutura e imagens.
- **L4 — Due diligence:** L3 + matrícula/certidões/documentos restritos obtidos por canal oficial ou pelo usuário.

A meta antes da VM/ZoLa nacional é levar as cidades prioritárias a **L3**, deixando L4 disponível como fluxo sob demanda.

## Princípio de evidência

Cada campo precisa carregar:
- valor;
- unidade;
- fonte;
- autoridade;
- URL/documento;
- data de captura;
- validade temporal;
- licença/classe de acesso;
- geometria aplicável;
- método;
- confiança;
- hash quando houver arquivo;
- indicação de oficial, derivado ou informado pelo usuário.

## O que não deve ser achatado

Não tratar como se fossem a mesma coisa:
- lote municipal;
- unidade fiscal/IPTU;
- matrícula;
- unidade condominial;
- endereço;
- edificação;
- CIB;
- CAR;
- parcela SIGEF.

O produto reconciliará esses identificadores, preservando divergências.

## Matrícula e titularidade

Matrícula, certidões, ônus e titularidade entram no **L4**.

O sistema deve:
1. identificar cartório/CNS quando possível;
2. permitir pedido oficial via RI Digital/Meu Registro ou upload do usuário;
3. guardar o documento em área privada;
4. extrair fatos com proveniência;
5. nunca transformar nomes/CPFs em mecanismo público nacional de busca.

## Critério para considerar uma cidade “terminada”

Uma cidade entra como **L3 pronta para produção** somente quando temos, no mínimo:

- lote/geometria ou identificação espacial confiável;
- cadastro municipal/identificador;
- Plano Diretor + zoneamento vigente;
- parâmetros construtivos estruturáveis;
- edificação ou atributos prediais;
- IPTU/PGV ou equivalente, quando publicado;
- ITBI/transações quando publicado;
- licenciamento/projetos/habite-se quando disponível;
- restrições ambientais e risco;
- infraestrutura relevante;
- imagem/ortofoto ou referência visual licenciada;
- histórico jurídico básico;
- regras explícitas de licença/LGPD;
- conector/snapshot reprodutível.

Ausência de uma fonte pública não bloqueia para sempre a cidade: o dossiê deve mostrar **“não disponível publicamente / aquisição sob demanda / usuário pode fornecer”**.

## Resultado de tela

A ficha final deve responder:

- **Que imóvel é este?**
- **Qual a área e geometria?**
- **O que existe construído?**
- **Quanto o município considera que vale?**
- **Que transações conhecemos?**
- **O que pode ser construído?**
- **Quais licenças e projetos existem?**
- **Quais restrições ambientais, patrimoniais e de risco incidem?**
- **Que infraestrutura passa aqui?**
- **Qual a matrícula/cartório e quais direitos/ônus foram comprovados?**
- **De onde veio cada afirmação?**
- **O que ainda não sabemos?**
