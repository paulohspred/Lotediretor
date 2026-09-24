# Source discovery tools

Ferramentas pequenas para descobrir metadados em interfaces públicas e documentadas.

## harvest.py

Suporta inicialmente:

- CKAN `package_search`;
- diretórios/serviços ArcGIS REST;
- WFS `GetCapabilities`.

A saída é JSON para revisão antes de qualquer inclusão automática no Source Registry.

### Exemplos

```bash
python tools/discovery/harvest.py ckan https://dados.recife.pe.gov.br --query IPTU
python tools/discovery/harvest.py ckan https://dados.fortaleza.ce.gov.br --query zoneamento
python tools/discovery/harvest.py arcgis https://esigportal2.recife.pe.gov.br/arcgis/rest/services/Planejamento/BASES_ZONEAMENTO_G_PD2020/FeatureServer
python tools/discovery/harvest.py wfs https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs
```

## Limites

O coletor é de **descoberta**, não autorização para copiar.

Antes de ingestão permanente é obrigatório registrar:
- autoridade;
- licença/termos;
- classificação de acesso;
- cobertura;
- atualização;
- schema;
- política de dados pessoais.

Não deve ser usado para contornar login, CAPTCHA, paywall ou proteção de acesso. Google Maps/Street View não são alvos de scraping.
