import logging


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
