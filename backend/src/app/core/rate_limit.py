"""Limitador de falhas de login em memória (janela deslizante). Suficiente para um processo
único; com várias réplicas o estado deveria ir para Redis/Mongo."""

import ipaddress
import time
from collections import defaultdict, deque


def ip_key(ip: str) -> str:
    """Chave de limite por IP: IPv6 vira o /64 (o cliente controla o /64 e giraria endereços); IPv4 fica exato."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address)
    return str(addr)


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

    def count(self, key: str) -> int:
        return len(self._prune(key, time.monotonic()))

    def is_blocked(self, key: str) -> bool:
        return self.count(key) >= self.max_failures

    def _purge_expired(self) -> None:
        now = time.monotonic()
        for key in list(self._failures):
            self._prune(key, now)

    def register_failure(self, key: str) -> None:
        """Tabela cheia de chaves vivas e `key` nova: evicta a mais antiga (inserida primeiro) para que um flood
        de chaves não bloqueie todo login novo, admin incluso. shortcut: o flood pode zerar o contador de uma
        vítima; com várias réplicas/limite por IP, mover para Redis/Mongo."""
        if key not in self._failures and len(self._failures) >= self.max_keys:
            self._purge_expired()
            if len(self._failures) >= self.max_keys:
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
