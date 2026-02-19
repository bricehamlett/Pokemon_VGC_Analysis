--H, G, and F most documented regulations
--Query to Find usage rates of Different tera types in Regulations H, G, F
WITH pokemon_in_event AS (
	SELECT COUNT(poke_dex) AS pokemon_count, t.event_id FROM team_pokemon tp
	JOIN teams t ON t.team_id = tp.team_id
	GROUP BY t.event_id
)
SELECT ROUND(COUNT(tp.tera_type)::NUMERIC / pe.pokemon_count * 100, 2) AS total_usage, tl.type_name, e.event_name, e.regulation FROM team_pokemon tp
JOIN teams t ON t.team_id = tp.team_id
JOIN events e ON e.event_id = t.event_id
JOIN type_lookup tl ON tl.type_id = tp.tera_type
JOIN pokemon_in_event pe ON pe.event_id = t.event_id
WHERE e.regulation IN ('H','G','F')
GROUP BY tl.type_name, e.regulation, e.event_name, pe.pokemon_count
ORDER BY total_usage DESC;


