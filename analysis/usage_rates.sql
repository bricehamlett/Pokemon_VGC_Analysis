--Find usage rates for a specific Pokemon for each event order by the most recent to least
--Can be generalized to get all usage rates for all tournaments in DB
WITH event_team_totals AS (
	SELECT event_id, COUNT(DISTINCT team_id) as teams_in_event
	FROM teams
	GROUP BY event_id
)
SELECT
  ROUND(COUNT(DISTINCT tp.team_id)::numeric / ett.teams_in_event * 100, 4) AS total,
  tp.poke_dex,
  t.event_id,
  e.event_name,
  e.event_date,
  p.pokemon_name
FROM team_pokemon tp
JOIN teams t   ON tp.team_id = t.team_id
JOIN events e  ON t.event_id = e.event_id
JOIN pokemon p ON p.poke_dex = tp.poke_dex
JOIN event_team_totals ett ON ett.event_id = e.event_id
GROUP BY t.event_id, tp.poke_dex, e.event_name, p.pokemon_name, e.event_size, ett.teams_in_event, e.event_date
HAVING ett.teams_in_event >= 60
AND p.pokemon_name = 'incineroar'
ORDER BY e.event_date DESC;



