import logging
import re
from urllib.parse import urlsplit, urlunsplit

_ZIP_PATH = re.compile(r"/shop/zip/\d{8}")
_ZIP_QUERY = re.compile(r"([?&]zip=)\d{5}(?:-|%2[dD])?\d{3}")  # frete: /shop/cart/freight e /shop/products/{id}/freight


class MaskZipFilter(logging.Filter):
    """O CEP completo não pode ir ao access log do uvicorn (args = cliente, método, path, versão, status)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _ZIP_QUERY.sub(r"\1XXXXX***", _ZIP_PATH.sub("/shop/zip/XXXXX***", a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def setup_logging() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, MaskZipFilter) for f in access.filters):
        access.addFilter(MaskZipFilter())
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
