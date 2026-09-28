# LoteDiretor Web

Novo cliente unificado conforme o Blueprint Final v2.0.

## Baseline

- React / Next.js.
- Design tokens LoteDiretor: #20A475, #356854, #1F4035, branco/ink.
- Shell de cliente com rail fixo, busca global, workspace/data-base e Explorer central.
- MapLibre GL + deck.gl como baseline 2D.
- Three.js/Cesium será introduzido no workspace 3D/A.I TEC.
- O cliente está em migração paralela: **não substitui a produção atual até atingir paridade funcional e passar E2E**.

## Runtime

Next.js 16 requer Node >= 20.9.0. O host legado atual usa Node 18; a promoção do novo cliente depende de atualização controlada do runtime/containers.

## Próximos gates

1. Conectar Parcel Resolver/search atuais por contrato versionado.
2. Migrar catálogo de camadas para MapLibre/deck.gl.
3. Introduzir Martin MVT para lotes/zoneamento de alto volume.
4. Migrar ficha e evidência.
5. Implementar login Keycloak/BFF.
6. E2E desktop/mobile + acessibilidade.
7. Canary em staging antes de trocar o web root.
