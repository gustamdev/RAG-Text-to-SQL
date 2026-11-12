import subprocess

from app.config import settings


def start_mongo_container() -> None:
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(settings.compose_file), "up", "-d"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError("Não foi possível iniciar o container do MongoDB via docker compose.") from exc
