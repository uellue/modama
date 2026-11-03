-- Our crawler as the only endpoint that the test harvests (the upstream seed endpoints stay, but are never harvested).
INSERT INTO repositories (name, code, description, base_url, is_active)
VALUES ('ER-C test crawler', 'ERC', 'modama crawler OAI-PMH endpoint of the e2e test', 'http://crawler:7654', true);

INSERT INTO endpoints (repository_id, name, harvest_url, protocol, harvest_params, harvest_schedule, is_active)
SELECT id, 'ER-C test crawler', 'http://crawler:7654/oai', 'OAI-PMH',
       '{"metadata_prefix": "oai_dc"}'::jsonb, INTERVAL '1 day', true
FROM repositories WHERE code = 'ERC';
