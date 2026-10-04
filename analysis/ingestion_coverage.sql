-- Run after the additive ingestion migration.
SELECT e.source,
       e.regulation,
       COUNT(DISTINCT e.event_id) AS events,
       COUNT(t.team_id) AS entrants,
       COUNT(t.team_id) FILTER (WHERE t.sheet_status = 'missing') AS missing_sheets,
       COUNT(t.team_id) FILTER (WHERE t.sheet_status IN ('invalid', 'conflict')) AS flagged_sheets,
       COUNT(v.team_id) AS placement_training_teams
FROM events e
LEFT JOIN teams t ON t.event_id = e.event_id
LEFT JOIN training_team_entries v ON v.team_id = t.team_id
GROUP BY e.source, e.regulation
ORDER BY e.source, e.regulation;
