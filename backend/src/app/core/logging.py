import logging
from urllib.parse import urlsplit, urlunsplit


def setup_logging() -> None:
    # Só o namespace "app": INFO no root acenderia logs de pymongo/urllib/watchfiles.
    logger = logging.getLogger("app")
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # o uvicorn já tem handler próprio


def mask_uri(uri: str) -> str:
    """Esconde user:senha de uma URI (mongodb://user:pass@host) antes de logar, mesmo com '@' na senha."""
    parts = urlsplit(uri)
    if "@" not in parts.netloc:
        return uri
    return urlunsplit(parts._replace(netloc="***@" + parts.netloc.rpartition("@")[2]))
