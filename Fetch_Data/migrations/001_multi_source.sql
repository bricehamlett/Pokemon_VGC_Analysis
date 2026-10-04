-- Additive migration: retains existing event/team IDs and reference data.
-- Run through ingestion.migrate(), never through the destructive bootstrap schema.
CREATE TABLE IF NOT EXISTS ingestion_migrations (version TEXT PRIMARY KEY);

ALTER TABLE events DROP CONSTRAINT IF EXISTS events_event_name_key;
ALTER TABLE events ALTER COLUMN event_name TYPE TEXT;
ALTER TABLE events ALTER COLUMN regulation TYPE TEXT;
ALTER TABLE players ALTER COLUMN player_name TYPE TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS external_id TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS source_metadata JSONB NOT NULL DEFAULT '{}';
UPDATE events SET source = 'limitless_vgc', external_id = event_id::text WHERE source IS NULL;
ALTER TABLE events ALTER COLUMN source SET NOT NULL;
ALTER TABLE events ALTER COLUMN external_id SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS events_source_id ON events(source, external_id);
CREATE SEQUENCE IF NOT EXISTS ingestion_event_id_seq;
SELECT setval('ingestion_event_id_seq', GREATEST(COALESCE((SELECT MAX(event_id) FROM events), 0) + 1, 1), false);
ALTER TABLE events ALTER COLUMN event_id SET DEFAULT nextval('ingestion_event_id_seq');

CREATE TABLE IF NOT EXISTS player_sources (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    PRIMARY KEY(source, external_id)
);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS record JSONB;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS drop_round INTEGER;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS country TEXT;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS quality_issues JSONB NOT NULL DEFAULT '[]';
ALTER TABLE teams ADD COLUMN IF NOT EXISTS sheet_status TEXT NOT NULL DEFAULT 'legacy';

CREATE TABLE IF NOT EXISTS ingestion_snapshots (
    snapshot_id BIGSERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(event_id),
    payload_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    UNIQUE(event_id, payload_hash)
);
CREATE TABLE IF NOT EXISTS event_pairings (
    event_id INTEGER NOT NULL REFERENCES events(event_id),
    pairing_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY(event_id, pairing_key)
);

-- Missing Tera/build fields may be used by composition-only models. Errors,
-- missing sheets, and conflicting refreshes are excluded from this view.
CREATE OR REPLACE VIEW training_team_entries AS
SELECT t.* FROM teams t JOIN events e USING(event_id)
WHERE t.placement IS NOT NULL AND t.placement BETWEEN 1 AND e.event_size
  AND e.event_size > 1
  AND t.sheet_status IN ('complete', 'partial', 'legacy')
  AND NOT EXISTS (
      SELECT 1 FROM jsonb_array_elements_text(t.quality_issues) AS q(issue)
      WHERE q.issue LIKE 'error:%'
  )
  AND (SELECT count(*) FROM team_pokemon p WHERE p.team_id = t.team_id) = 6;

INSERT INTO ingestion_migrations(version) VALUES ('001_multi_source') ON CONFLICT DO NOTHING;
