"""Start all Docker services for the Pokémon VGC application."""

from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
DOCKER_DIRECTORY = PROJECT_ROOT / "Fetch_Data"
COMPOSE_FILE = DOCKER_DIRECTORY / "compose.yaml"
ENV_FILE = DOCKER_DIRECTORY / ".env"


def main() -> int:
    """Build and start the application's Docker services."""

    if shutil.which("docker") is None:
        print("Docker was not found. Install or start Docker Desktop first.")
        return 1

    if not COMPOSE_FILE.exists():
        print(f"Compose file not found: {COMPOSE_FILE}")
        return 1

    if not ENV_FILE.exists():
        print(f"Environment file not found: {ENV_FILE}")
        print("Copy Fetch_Data/.env.example to Fetch_Data/.env first.")
        return 1

    command = [
        "docker",
        "compose",
        "--env-file",
        str(ENV_FILE),
        "--file",
        str(COMPOSE_FILE),
        "up",
        "--build",
    ]

    print("Starting Pokémon VGC services...")
    print("Press Ctrl+C to stop them.\n")

    try:
        return subprocess.run(
            command,
            cwd=DOCKER_DIRECTORY,
            check=False,
        ).returncode
    except KeyboardInterrupt:
        print("\nDocker services stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())