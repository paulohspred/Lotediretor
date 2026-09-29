-- Test-only catalog source used by the factory fixture spec.
INSERT INTO ld_catalog.source
    (source_id, authority, scope, source_type, access_class, license,
     verification_status, coverage_level, uf, municipality_ibge, domains)
VALUES
    ('test-fixture-municipal-gis', 'Fixture', '3159605', 'GEOJSON',
     'OPEN_REUSABLE', 'synthetic', 'TEST_FIXTURE', 'MUNICIPAL', 'MG',
     '3159605', ARRAY['lots', 'zoning'])
ON CONFLICT (source_id) DO NOTHING;
