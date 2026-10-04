# Docker setup for the VGC scraper

## Project services

- `db`: PostgreSQL 18.6 with persistent Docker storage.
- `seed`: verifies Pokémon, moves, abilities, and items against PokeAPI catalogs;
  completed records are checkpointed, cached, and skipped on subsequent runs.
- `scraper`: runs `scraping_limitless.py` after seeding succeeds.
- `api`: imports all advertised VGC formats after seeding, skipping older committed
  events and refreshing events started in the last 14 days. First-run backfills
  are uncapped; raw snapshots and run reports persist under `Fetch_Data/data/`.

From the repository root, `python start_app.py` runs both collectors. Use
`python start_app.py --api-max-events 2` for a bounded API import of two events per
format. See [the ingestion guide](Fetch_Data/API_INGESTION.md) for audit-only runs,
quality checks, and verification queries.

## First run

1. Install Docker Desktop (or Docker Engine + Compose).
2. Copy `.env.example` to `.env`.
3. Change `POSTGRES_PASSWORD` in `.env`.
4. From this directory run:

   ```bash
   docker compose up --build
   ```

The first run takes longer because the seed service downloads reference data from PokeAPI.
Slow requests are retried up to four times with a 45-second read timeout. If a
request still fails, successfully committed records remain saved. Rerun
`python start_app.py` from the repository root to resume; do not reset the database.
Existing rows created by the old seeder are verified once to establish checkpoints.

Catalogs are cached for 24 hours, and resource details persist under
`Fetch_Data/data/pokeapi/`. Both cache and database checkpoints survive container
restarts. Reference verification always runs before tournament ingestion; a table
having some rows is no longer treated as proof that seeding finished.

## Database connection from your computer

Use:

- Host: `127.0.0.1`
- Port: `5433`
- Database: value of `POSTGRES_DB`
- User: value of `POSTGRES_USER`
- Password: value of `POSTGRES_PASSWORD`

Inside Docker, Python connects to `db:5432` instead.

## Useful commands

Start everything:

```bash
docker compose up --build
```

Run in the background:

```bash
docker compose up --build -d
```

See scraper logs:

```bash
docker compose logs -f scraper
```

Open a PostgreSQL shell:

```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Stop containers but keep database data:

```bash
docker compose down
```

Delete containers AND the PostgreSQL volume, forcing a totally fresh database next run:

```bash
docker compose down -v
```

## Important initialization behavior

The SQL files in `/docker-entrypoint-initdb.d` run only when PostgreSQL initializes an empty data volume. Editing `01_schema.sql` later will not automatically modify an already-created database. For schema evolution, use migrations or deliberately recreate the development volume with `docker compose down -v` if losing the local data is acceptable.
