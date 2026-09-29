SELECT
    t.team_id,
    t.event_id,
    e.event_date,
    e.regulation,
    t.placement,
    e.event_size,

    tp.slot,
    p.pokemon_name,
    i.item_name,
    a.ability_name,
    tera.type_name AS tera_type,

    m.move_name

FROM Teams t

JOIN Events e
    ON t.event_id = e.event_id

JOIN Team_Pokemon tp
    ON t.team_id = tp.team_id

JOIN Pokemon p
    ON tp.pk_id = p.pk_id

LEFT JOIN Items i
    ON tp.item_id = i.item_id

LEFT JOIN Abilities a
    ON tp.ability_id = a.ability_id

LEFT JOIN Type_lookup tera
    ON tp.tera_type = tera.type_id

LEFT JOIN Team_Pokemon_Moves tpm
    ON tp.team_pokemon_id = tpm.team_pokemon_id

LEFT JOIN Moves m
    ON tpm.move_id = m.move_id
WHERE regulation = :regulation
ORDER BY
    e.event_date,
    t.team_id,
    tp.slot,
    tpm.move_slot;
	