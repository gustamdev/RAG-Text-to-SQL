"""Refresh do snapshot DuckDB do agente: debounce, single-flight, em segundo plano, nunca lança.

`request()` é o gancho barato (checkout pago, exclusão de cliente): agenda um rebuild daqui a
`debounce_s`; pedidos no meio da espera viram um só. `refresh()` roda já (admin) e se junta a um
rebuild em andamento em vez de iniciar outro. O build é síncrono (pymongo + DuckDB), então roda numa
thread; a troca do motor é `SQLEngine.reload()` (não derruba consultas em voo).
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime

from app.core.timeutil import now
from app.database.sql_engine import SQLEngine

logger = logging.getLogger(__name__)


@dataclass
class SnapshotState:
    in_progress: bool = False
    pending: bool = False  # há um rebuild agendado (debounce) ainda não iniciado
    last_started_at: datetime | None = None
    last_built_at: datetime | None = None  # watermark: dados da loja até este instante estão no agente
    last_error: str | None = None
    builds: int = 0


class SnapshotService:
    def __init__(
        self,
        engine: SQLEngine,
        build: Callable[[], bool],
        *,
        debounce_s: float = 3.0,
        on_swap: Callable[[set[str]], None] | None = None,
    ):
        self.engine = engine
        self._build = build
        self.debounce_s = debounce_s
        self._on_swap = on_swap
        self.state = SnapshotState()
        self._flight: asyncio.Task | None = None
        self._timer: asyncio.Task | None = None

    def status(self) -> dict:
        return asdict(self.state)

    async def request(self) -> None:
        """Agenda um rebuild com debounce. Nunca lança nem espera o build."""
        try:
            if not self.state.pending:
                self.state.pending = True
                self._timer = asyncio.create_task(self._debounced())
        except Exception:
            logger.exception("Falha ao agendar refresh do snapshot")

    async def refresh(self) -> dict:
        """Roda um rebuild agora, ou se junta ao que já está rodando. Nunca lança."""
        if self._flight is None or self._flight.done():
            self._flight = asyncio.create_task(self._run())
        await asyncio.shield(self._flight)
        return self.status()

    async def _debounced(self) -> None:
        try:
            await asyncio.sleep(self.debounce_s)
            # A partir daqui um novo request() agenda outro rebuild: este pode já ter lido os dados.
            self.state.pending = False
            if self._flight is not None and not self._flight.done():
                await asyncio.shield(self._flight)  # o build em curso pode não ter visto o pedido novo
                self._flight = None
            await self.refresh()
        except Exception:
            self.state.pending = False
            logger.exception("Falha no refresh agendado do snapshot")

    async def _run(self) -> None:
        state = self.state
        state.in_progress, state.last_started_at = True, now()
        try:
            if await asyncio.to_thread(self._build):
                await self.engine.reload()
                if self._on_swap:
                    self._on_swap(self.engine.tables)
                state.last_built_at, state.builds = now(), state.builds + 1
            state.last_error = None
        except Exception as exc:
            # Só o tipo: a mensagem do driver pode trazer trecho de documento (PII) e vai para o admin.
            state.last_error = type(exc).__name__
            logger.exception("Falha ao reconstruir o snapshot do agente")
        finally:
            state.in_progress = False

    async def aclose(self) -> None:
        for task in (self._timer, self._flight):
            if task is not None and not task.done():
                task.cancel()
