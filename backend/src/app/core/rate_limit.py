"""Limitador de falhas de login em memória (janela deslizante). Suficiente para um processo
único; com várias réplicas o estado deveria ir para Redis/Mongo."""

import time
from collections import defaultdict, deque


class FailureLimiter:
    def __init__(self, max_failures: int, window_s: float, max_keys: int = 10_000):
        self.max_failures = max_failures
        self.window_s = window_s
        self.max_keys = max_keys
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._failures[key]
        while events and now - events[0] > self.window_s:
            events.popleft()
        if not events:
            self._failures.pop(key, None)
            return deque()
        return events

    def is_blocked(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) >= self.max_failures

    def register_failure(self, key: str) -> None:
        if len(self._failures) >= self.max_keys and key not in self._failures:
            self._failures.pop(next(iter(self._failures)))
        self._failures[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


class SlidingWindowLimiter:
    """Limite de N eventos por janela (s) por chave, em memória. Diferente do FailureLimiter,
    todo evento conta, não só as falhas: serve para limitar uso (ex.: perguntas ao chat por admin)."""

    def __init__(self, max_events: int, window_s: float, max_keys: int = 10_000):
        self.max_events = max_events
        self.window_s = window_s
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        """Registra o evento e devolve True se ainda cabe na janela; False (sem registrar) se estourou."""
        now = time.monotonic()
        events = self._events.get(key)
        if events is None:
            if len(self._events) >= self.max_keys:
                self._events.pop(next(iter(self._events)))
            events = self._events[key] = deque()
        while events and now - events[0] > self.window_s:
            events.popleft()
        if len(events) >= self.max_events:
            return False
        events.append(now)
        return True
