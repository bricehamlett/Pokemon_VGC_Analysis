-- Takes in Regulation Parameter and number of teams and gives a table with the top X usage rates

WITH eligible_events AS (
    SELECT
        e.event_id,
        e.regulation,
        ett.teams_in_event
    FROM events e
    JOIN event_team_totals ett
        ON ett.event_id = e.event_id
    WHERE e.regulation = :regulation          -- Change regulation here
      AND ett.teams_in_event >= :min_event_size
),

total_teams AS (
    SELECT
        SUM(teams_in_event) AS team_count
    FROM eligible_events
),

pokemon_usage AS (
    SELECT
        tp.poke_dex,
        p.pokemon_name,
        COUNT(DISTINCT tp.team_id) AS teams_using_pokemon
    FROM team_pokemon tp
    JOIN teams t
        ON tp.team_id = t.team_id
    JOIN eligible_events ee
        ON t.event_id = ee.event_id
    JOIN pokemon p
        ON p.pk_id = tp.pk_id
    GROUP BY
        tp.poke_dex,
        p.pokemon_name
)

SELECT
    pu.poke_dex,
    pu.pokemon_name,
    pu.teams_using_pokemon,
    tt.team_count AS total_teams,
    ROUND(
        pu.teams_using_pokemon::numeric
        / tt.team_count
        * 100,
        2
    ) AS usage_percent
FROM pokemon_usage pu
CROSS JOIN total_teams tt
ORDER BY usage_percent DESC
LIMIT :num_pokemon;