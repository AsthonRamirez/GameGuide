"""Límite de peticiones por IP (ventana deslizante en memoria). Suficiente para un único proceso."""
from __future__ import annotations
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config as cfg


class RateLimiter:
    def __init__(self, max_calls: int, window_s: int = 60, name: str = "api"):
        self.max_calls, self.window_s, self.name = max_calls, window_s, name
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    @staticmethod
    def client_ip(request: Request) -> str:
        if cfg.TRUST_PROXY_HEADERS:  # solo si hay un proxy de confianza delante (Nginx, Render, etc.)
            fwd = request.headers.get("x-forwarded-for")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def __call__(self, request: Request) -> None:
        if self.max_calls <= 0:
            return
        ip, now = self.client_ip(request), time.monotonic()
        with self._lock:
            hits = self._hits[ip]
            while hits and now - hits[0] > self.window_s:
                hits.popleft()
            if len(hits) >= self.max_calls:
                retry = int(self.window_s - (now - hits[0])) + 1
                raise HTTPException(429, f"Demasiadas consultas. Intenta de nuevo en {retry} s.",
                                    headers={"Retry-After": str(retry)})
            hits.append(now)
            if now - self._last_cleanup > 300:  # limpieza periódica de IPs inactivas
                for key in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window_s]:
                    del self._hits[key]
                self._last_cleanup = now


limit_chat = RateLimiter(cfg.RATE_LIMIT_CHAT_PER_MIN, name="chat")
limit_vote = RateLimiter(cfg.RATE_LIMIT_VOTE_PER_MIN, name="vote")
