from __future__ import annotations

import threading
import time

import httpx

from truevision_shared.config import AppConfig


class ServerConnection:
    def __init__(self, config: AppConfig, logger) -> None:
        self._config = config
        self._logger = logger
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._server_url: str | None = config.server_url
        self._available = bool(config.server_url)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="truevision-server-health", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def is_available(self) -> bool:
        with self._lock:
            return self._available

    @property
    def server_url(self) -> str | None:
        with self._lock:
            return self._server_url

    def summarize(self, *, transcript: str, previous_summary: str | None, person_name: str | None, max_chars: int) -> str | None:
        server_url = self.server_url
        if not server_url:
            return None
        try:
            response = httpx.post(
                f"{server_url.rstrip('/')}/summarize",
                json={
                    "transcript": transcript,
                    "previous_summary": previous_summary,
                    "person_name": person_name,
                    "max_chars": max_chars,
                },
                timeout=self._config.server_connect_timeout_sec,
            )
            response.raise_for_status()
        except Exception as exc:
            self._logger.warning("remote summarize failed", extra={"error": str(exc)})
            return None
        payload = response.json()
        return str(payload.get("summary", "")).strip() or None

    def send_command(self, endpoint: str, *, command: str) -> dict[str, object] | None:
        server_url = self.server_url
        if not server_url:
            return None
        try:
            response = httpx.post(
                f"{server_url.rstrip('/')}/{endpoint.lstrip('/')}",
                json={"command": command},
                timeout=self._config.server_connect_timeout_sec,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            self._logger.warning("remote command failed", extra={"endpoint": endpoint, "error": str(exc)})
            return None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            available = False
            server_url = self._server_url
            if server_url:
                try:
                    response = httpx.get(
                        f"{server_url.rstrip('/')}/health",
                        timeout=self._config.server_connect_timeout_sec,
                    )
                    response.raise_for_status()
                    available = True
                except Exception:
                    available = False
            with self._lock:
                self._available = available
            self._stop_event.wait(self._config.server_health_interval_sec)
