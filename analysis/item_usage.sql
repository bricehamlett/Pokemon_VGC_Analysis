--Query to find most used item for each pokemon 
WITH total_pokemon_entered AS (
	SELECT COUNT(poke_dex) AS total_pokemon, poke_dex FROM team_pokemon
	GROUP BY poke_dex
)
SELECT ROUND(COUNT(*)::NUMERIC / tpe.total_pokemon * 100, 2) as total_item_usage, p.pokemon_name, i.item_name FROM team_pokemon tp
JOIN items i ON i.item_id = tp.item_id
JOIN pokemon p ON p.poke_dex = tp.poke_dex
JOIN total_pokemon_entered tpe ON tpe.poke_dex = tp.poke_dex
GROUP BY i.item_name, p.pokemon_name, tpe.total_pokemon
ORDER BY total_item_usage DESC