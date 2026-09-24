# Estratégia de Imagem, Relevo e Cortes do Terreno

**Data:** 24/09/2026

O LoteDiretor deve produzir uma leitura visual e topográfica do imóvel, mas precisa diferenciar com precisão:

- **visualização de contexto**;
- **dado analisável/licenciado**;
- **estimativa derivada**;
- **levantamento topográfico de engenharia**.

## 1. Google Maps, Google Earth e Street View

Google é valioso para navegação e contexto visual, mas não deve ser nossa base persistente de análise.

### Permitido no produto, conforme produto/termos aplicáveis

- abrir Google Maps/Google Earth para consulta;
- integrar Google Maps Platform quando houver contrato/API adequada;
- incorporar Street View por API/embeds compatíveis;
- guardar IDs permitidos pelos termos, quando aplicável;
- mostrar link para o usuário abrir a localização em Google Maps/Earth.

### Não usar como pipeline de dados

- baixar tiles em massa;
- armazenar/cachar imagens permanentemente fora das exceções dos termos;
- raspar Street View;
- traçar footprints, vias ou postes a partir da imagem Google;
- reconstruir prédio 3D;
- criar DTM/DSM a partir de Google Elevation/Google Earth;
- usar Google Maps como fonte para point-in-polygon cadastral;
- treinar modelos com conteúdo Google Maps.

Para um relatório comercial do LoteDiretor, o padrão deve ser **imagem persistente proveniente de fonte governamental/aberta/licenciada**. Google pode permanecer como referência interativa.

## 2. Earth Engine

Google Earth Engine é útil como **infraestrutura de processamento**, não como uma licença única de dados.

O catálogo possui imagens, elevação, uso do solo, clima e outros datasets. Cada dataset conserva seus termos.

Para operação comercial do LoteDiretor:
- usar configuração/plano comercial quando a computação ocorrer via Earth Engine;
- registrar o dataset original e sua licença;
- preferir download direto da fonte quando isso simplificar licença/custo;
- jamais misturar a regra do Earth Engine com a de Google Maps: são produtos diferentes.

## 3. Hierarquia de fonte de relevo

### T0 — Levantamento topográfico do imóvel

Exemplos:
- RTK/GNSS;
- estação total;
- levantamento cadastral/topográfico;
- nuvem de pontos entregue pelo cliente;
- levantamento assinado com ART/RRT.

Uso: **engenharia/projeto executivo**, sujeito à responsabilidade do profissional.

### T1 — LiDAR/MDT/levantamento aerofotogramétrico municipal ou estadual

Exemplos:
- MDT municipal;
- nuvem LiDAR;
- curvas 0,5 m/1 m;
- aerofotogrametria oficial de alta resolução.

Uso: excelente para estudo preliminar e muitas análises urbanísticas. Verificar época, datum, precisão e se é DTM (solo) ou DSM/MDS (superfície).

### T2 — Modelo oficial regional de resolução intermediária

Exemplos:
- levantamentos estaduais;
- SGB/local;
- produtos específicos de bacia/risco.

### T3 — DEM/DSM global ~30 m

Exemplos:
- Copernicus DEM GLO-30;
- JAXA AW3D30.

Uso: **contexto regional/preliminar**, especialmente em lotes grandes. Em lote urbano pequeno, 30 m pode não representar corretamente a topografia interna.

### T4 — DEM global 90 m ou equivalente

Exemplo:
- Copernicus GLO-90.

Uso: contexto regional. Não produzir alegações de engenharia em lote pequeno.

## 4. Produtos topográficos do relatório

Quando a resolução permitir, calcular:

- cota mínima;
- cota máxima;
- cota média;
- amplitude altimétrica;
- declividade média;
- declividade máxima;
- orientação/aspect dominante;
- percentual do lote por classe de declividade;
- curvas de nível derivadas;
- hillshade;
- mapa hipsométrico;
- pontos altos/baixos;
- escoamento superficial aproximado;
- depressões aparentes;
- relação com rua/testada;
- diferença de cota entre testada e fundos.

### Cortes automáticos

Gerar, quando tecnicamente defensável:

1. **Perfil A-A — eixo principal do lote**
   - maior eixo interno/oriented minimum bounding rectangle.

2. **Perfil B-B — transversal**
   - perpendicular ao eixo principal, passando pelo centroide ou região representativa.

3. **Testada → fundos**
   - quando a testada puder ser identificada em relação ao logradouro.

4. **Diagonais**
   - úteis em lotes irregulares ou com forte variação de relevo.

5. **Perfil rua + lote**
   - incluir trecho da via e calçada quando o modelo de elevação possuir precisão suficiente.

Cada perfil deve trazer:
- distância acumulada;
- cota;
- fonte do DEM;
- resolução nominal;
- data;
- método de interpolação;
- datum vertical/horizontal quando conhecido;
- qualidade/nível T0–T4.

## 5. Corte e aterro

O LoteDiretor pode produzir uma **estimativa preliminar** de corte/aterro quando houver:
- DTM com resolução/precisão compatível;
- geometria de plataforma proposta;
- datum conhecido;
- parâmetros explícitos.

Nunca apresentar volume derivado de DEM 30/90 m como quantitativo executivo.

Rotulagem:
- `PRELIMINARY_TERRAIN_ESTIMATE`;
- `ENGINEERING_SURVEY_REQUIRED`.

## 6. Imagens do imóvel

Prioridade:

1. ortofoto municipal/estadual oficial;
2. aerofotogrametria oficial histórica;
3. INPE/CBERS/Amazonia-1;
4. Copernicus Sentinel;
5. Mapillary para fachada/nível da rua;
6. imagem enviada pelo usuário;
7. Google Maps/Earth/Street View como referência interativa, não como nosso arquivo-base.

## 7. Edificações e altura

Hierarquia:

1. cadastro/levantamento municipal oficial;
2. LiDAR municipal/estadual;
3. projeto aprovado/alvará/habite-se;
4. Open Buildings 2.5D;
5. Overture/OSM/Open Buildings polygons;
6. inferência própria claramente marcada.

O Open Buildings 2.5D fornece presença e altura estimada, mas é **modelo derivado**, não gabarito legal nem altura oficial.

## 8. Histórico visual

Quando houver:
- ortofotos de anos diferentes;
- CBERS/Landsat/Sentinel;
- Open Buildings Temporal 2016–2023;
- MapBiomas;
- fotos históricas municipais;

o relatório pode indicar mudanças como:
- edificação aparece/desaparece;
- expansão de footprint;
- adensamento;
- mudança de cobertura do solo;
- vegetação/supressão aparente;
- água/inundação histórica;
- alteração viária.

Toda detecção automática deve ser marcada como `DERIVED` até confirmação documental.

## 9. Resultado esperado

O relatório deve conter uma seção semelhante a:

**Topografia**
- Fonte: LiDAR Prefeitura, 2024
- Resolução: 0,5 m
- Cota mínima: …
- Cota máxima: …
- Desnível testada–fundos: …
- Declividade média: …
- Perfis A-A e B-B
- Observação: estudo preliminar; confirmar em levantamento topográfico para projeto executivo.

**Imagem**
- Ortofoto oficial: …
- Imagem histórica: …
- Fachada Mapillary: …
- Abrir Google Street View: link/integração

**Edificação**
- footprint oficial/estimado;
- altura oficial/estimada;
- área construída fiscal;
- área aprovada;
- divergências entre fontes.
