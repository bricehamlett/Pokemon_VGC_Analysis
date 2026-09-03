# Docker setup for the VGC scraper

## Project services

- `db`: PostgreSQL 18.6 with persistent Docker storage.
- `seed`: one-shot Python job that fills Pokemon, moves, abilities, and items when those tables are empty.
- `scraper`: runs `scraping_limitless.py` after seeding succeeds.

## First run

1. Install Docker Desktop (or Docker Engine + Compose).
2. Copy `.env.example` to `.env`.
3. Change `POSTGRES_PASSWORD` in `.env`.
4. From this directory run:

   ```bash
   docker compose up --build
   ```

The first run takes longer because the seed service downloads reference data from PokeAPI.

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
