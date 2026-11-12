import socket

import uvicorn

from app.config import settings


def get_dev_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def print_banner(host: str, port: int) -> None:
    rows = [
        "Olist Insights API",
        f"Servidor: http://{host}:{port}",
        f"Docs:     http://{host}:{port}/docs",
    ]
    width = max(len(row) for row in rows) + 2
    lines = [f"║ {row.ljust(width - 2)} ║" for row in rows]
    print(
        "\n".join(
            [
                f"╔{'═' * width}╗",
                lines[0],
                f"╠{'═' * width}╣",
                *lines[1:],
                f"╚{'═' * width}╝",
            ]
        )
    )


if __name__ == "__main__":
    print_banner(get_dev_ip(), settings.PORT)
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=not settings.is_prod,
        reload_dirs=["src"],
    )
