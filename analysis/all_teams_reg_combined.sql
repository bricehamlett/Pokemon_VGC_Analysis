-- Requires the additive ingestion migration. Use this query for mixed-source ML.
-- Missing Tera/build fields are retained; filter sheet_status='complete' for full-build models.
SELECT t.team_id, t.event_id, e.event_date, e.regulation, t.placement, e.event_size,
       e.source, e.external_id, e.source_metadata, t.sheet_status, t.quality_issues,
       t.record, t.drop_round,
       tp.slot, p.pokemon_name, i.item_name, a.ability_name, tera.type_name AS tera_type,
       m.move_name
FROM training_team_entries t
JOIN events e ON t.event_id = e.event_id
JOIN team_pokemon tp ON t.team_id = tp.team_id
JOIN pokemon p ON tp.pk_id = p.pk_id
LEFT JOIN items i ON tp.item_id = i.item_id
LEFT JOIN abilities a ON tp.ability_id = a.ability_id
LEFT JOIN type_lookup tera ON tp.tera_type = tera.type_id
LEFT JOIN team_pokemon_moves tpm ON tp.team_pokemon_id = tpm.team_pokemon_id
LEFT JOIN moves m ON tpm.move_id = m.move_id
WHERE e.regulation = :regulation
ORDER BY e.event_date, t.team_id, tp.slot, tpm.move_slot;
