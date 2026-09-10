"""Start the Pokémon VGC application."""

from pathlib import Path
import shutil
import subprocess
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parent
DOCKER_DIRECTORY = PROJECT_ROOT / "Fetch_Data"
COMPOSE_FILE = DOCKER_DIRECTORY / "compose.yaml"
ENV_FILE = DOCKER_DIRECTORY / ".env"


def compose_command(*args):
    """Create a docker compose command using this project's files."""
    return [
        "docker",
        "compose",
        "--env-file",
        str(ENV_FILE),
        "--file",
        str(COMPOSE_FILE),
        *args,
    ]


def wait_for_database():
    """Wait until PostgreSQL is ready to accept queries."""

    print("Waiting for database...")

    for _ in range(30):
        result = subprocess.run(
            compose_command(
                "exec",
                "-T",
                "db",
                "sh",
                "-c",
                'psql -U "$POSTGRES_USER" '
                '-d "$POSTGRES_DB" '
                '-tAc "SELECT 1;"',
            ),
            cwd=DOCKER_DIRECTORY,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print("Database is ready.")
            return True

        time.sleep(1)

    print("Database did not become ready.")
    return False


def database_is_seeded():
    """
    Check whether the important reference tables contain data.

    If all four contain at least one row, consider the database seeded.
    """

    query = """
    SELECT CASE
        WHEN EXISTS (SELECT 1 FROM pokemon)
         AND EXISTS (SELECT 1 FROM moves)
         AND EXISTS (SELECT 1 FROM abilities)
         AND EXISTS (SELECT 1 FROM items)
        THEN 1
        ELSE 0
    END;
    """

    result = subprocess.run(
        compose_command(
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            f'''psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "{query}"''',
        ),
        cwd=DOCKER_DIRECTORY,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("Could not check database contents.")
        print(result.stderr)
        return False

    return result.stdout.strip() == "1"


def main() -> int:

    # -------------------------
    # Basic checks
    # -------------------------

    if shutil.which("docker") is None:
        print("Docker was not found. Start Docker Desktop first.")
        return 1

    if not COMPOSE_FILE.exists():
        print(f"Compose file not found: {COMPOSE_FILE}")
        return 1

    if not ENV_FILE.exists():
        print(f"Environment file not found: {ENV_FILE}")
        return 1

    # -------------------------
    # Start database + pgAdmin
    # -------------------------

    print("\nStarting database and pgAdmin...")

    result = subprocess.run(
        compose_command(
            "up",
            "-d",
            "db",
            "pgadmin",
        ),
        cwd=DOCKER_DIRECTORY,
    )

    if result.returncode != 0:
        return result.returncode

    # -------------------------
    # Wait for PostgreSQL
    # -------------------------

    if not wait_for_database():
        return 1

    # -------------------------
    # Build Python containers
    # -------------------------

    print("\nBuilding application containers...")

    result = subprocess.run(
        compose_command(
            "build",
            "seed",
            "scraper",
        ),
        cwd=DOCKER_DIRECTORY,
    )

    if result.returncode != 0:
        return result.returncode

    # -------------------------
    # Check seed status
    # -------------------------

    print("\nChecking database...")

    if database_is_seeded():

        print("Database already populated.")
        print("Skipping seed.")

    else:

        print("Database is empty or incomplete.")
        print("Running seed...\n")

        result = subprocess.run(
            compose_command(
                "run",
                "--rm",
                "seed",
            ),
            cwd=DOCKER_DIRECTORY,
        )

        if result.returncode != 0:
            print("Database seeding failed.")
            return result.returncode

        print("\nDatabase seeded successfully.")

    # -------------------------
    # Run scraper
    # -------------------------

    print("\nStarting Limitless scraper...\n")

    try:
        result = subprocess.run(
            compose_command(
                "run",
                "--rm",
                "--no-deps",
                "scraper",
            ),
            cwd=DOCKER_DIRECTORY,
        )

        return result.returncode

    except KeyboardInterrupt:
        print("\nScraper stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())