"""Populate reference tables required by the Limitless VGC scraper.

Each stage is skipped when its target table already has rows, so this service is
safe to run on subsequent `docker compose up` commands without re-downloading
all PokeAPI data every time.
"""

import pokemon_table

POKEMON_URL = "https://pokeapi.co/api/v2/pokemon/"


def table_has_rows(table_name: str) -> bool:
    allowed = {"pokemon", "moves", "abilities", "items"}
    if table_name.lower() not in allowed:
        raise ValueError(f"Unsupported table: {table_name}")

    conn = pokemon_table.get_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)")
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()


def seed_pokemon() -> None:
    if table_has_rows("pokemon"):
        print("Pokemon already seeded; skipping.")
        return

    print("Seeding Pokemon and Pokemon_types...")
    conn = pokemon_table.get_connection()
    cur = conn.cursor()
    # This existing project function commits and closes its own cursor/connection.
    pokemon_table.commit_to_pokemon(cur, conn, POKEMON_URL)


def seed_with_cursor(table_name: str, function) -> None:
    if table_has_rows(table_name):
        print(f"{table_name} already seeded; skipping.")
        return

    print(f"Seeding {table_name}...")
    conn = pokemon_table.get_connection()
    cur = conn.cursor()
    try:
        function(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def main() -> None:
    seed_pokemon()
    seed_with_cursor("moves", pokemon_table.commit_to_moves)
    seed_with_cursor("abilities", pokemon_table.commit_to_abilities)
    seed_with_cursor("items", pokemon_table.commit_to_items)
    print("Database reference data is ready.")


if __name__ == "__main__":
    main()
