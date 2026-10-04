-- Pending identities are retained separately; existing player/build rows stay intact.
CREATE TABLE IF NOT EXISTS pending_identity_reviews (
    event_id INTEGER NOT NULL REFERENCES events(event_id),
    review_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    blocked_player_ids INTEGER[] NOT NULL DEFAULT '{}',
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    PRIMARY KEY(event_id, review_key)
);
CREATE OR REPLACE VIEW training_team_entries AS
SELECT t.* FROM teams t JOIN events e USING(event_id)
WHERE t.placement IS NOT NULL AND t.placement BETWEEN 1 AND e.event_size
  AND e.event_size > 1
  AND t.sheet_status IN ('complete', 'partial', 'legacy')
  AND NOT EXISTS (
      SELECT 1 FROM jsonb_array_elements_text(t.quality_issues) AS q(issue)
      WHERE q.issue LIKE 'error:%'
  )
  AND (SELECT count(*) FROM team_pokemon p WHERE p.team_id = t.team_id) = 6
  AND NOT EXISTS (
      SELECT 1 FROM pending_identity_reviews r
      WHERE r.event_id=t.event_id AND r.resolved_at IS NULL
        AND t.player_id = ANY(r.blocked_player_ids)
  );
INSERT INTO ingestion_migrations(version) VALUES ('002_identity_reviews') ON CONFLICT DO NOTHING;
