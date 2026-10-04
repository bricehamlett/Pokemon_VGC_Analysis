"""Start the Pokémon VGC application."""

from pathlib import Path
import argparse
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


def run_ingestion(api_max_events=None):
    """Run both collectors, attempt the API even if scraping fails."""
    failed = []
    for service in ('scraper', 'api'):
        print(f"\nStarting Limitless {service} ingestion...\n", flush=True)
        command = compose_command('run', '--rm', '--no-deps', service)
        if service == 'api':
            command += ['--write']
            if api_max_events is not None:
                command += ['--max-events', str(api_max_events)]
        result = subprocess.run(command, cwd=DOCKER_DIRECTORY)
        if result.returncode:
            failed.append((service, result.returncode))
    if failed:
        print(f"Ingestion completed with failures: {failed}")
        return failed[0][1]
    print('\nBoth ingestion stages completed successfully.')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-max-events', type=int,
                        help='Optional API import cap per format for a bounded run; default: uncapped')
    args = parser.parse_args(argv)
    if args.api_max_events is not None and args.api_max_events < 1:
        parser.error('--api-max-events must be positive')

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
            "api",
        ),
        cwd=DOCKER_DIRECTORY,
    )

    if result.returncode != 0:
        return result.returncode

    # -------------------------
    # Check seed status
    # -------------------------

    print("\nVerifying and resuming reference-data seed...", flush=True)
    result = subprocess.run(
        compose_command('run', '--rm', '--no-deps', 'seed'),
        cwd=DOCKER_DIRECTORY,
    )
    if result.returncode != 0:
        print('Reference seeding is incomplete. Saved progress will resume on the next run.')
        return result.returncode

    # -------------------------
    # Run both ingestion sources
    # -------------------------

    try:
        return run_ingestion(args.api_max_events)

    except KeyboardInterrupt:
        print("\nIngestion interrupted; the next run can resume committed API events.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
