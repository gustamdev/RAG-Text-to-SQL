from datetime import datetime

from pydantic import BaseModel


class SnapshotStatus(BaseModel):
    in_progress: bool
    pending: bool
    last_started_at: datetime | None
    last_built_at: datetime | None  # watermark: a loja até este instante já está visível ao agente
    last_error: str | None
    builds: int
