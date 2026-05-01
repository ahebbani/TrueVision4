from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock

from .config import AppConfig, Mode


@dataclass(slots=True)
class PiStatus:
    requested_mode: str
    active_mode: str
    display_background: str
    server_connected: bool
    launcher: str | None


class PiRuntimeState:
    def __init__(self, config: AppConfig) -> None:
        self._lock = Lock()
        self._server_connected = bool(config.server_url)
        initial_mode = config.force_mode if config.force_mode is not Mode.AUTO else Mode.FACE
        self._requested_mode = initial_mode
        self._last_single_mode = initial_mode if initial_mode in {Mode.FACE, Mode.AUDIO} else Mode.FACE
        self._active_mode = self._resolve_active_mode(initial_mode, config.force_mode)
        self._display_background = config.display_background.value
        self._launcher: str | None = None
        self._forced_mode = config.force_mode

    def snapshot(self) -> PiStatus:
        with self._lock:
            return self._snapshot_unlocked()

    def set_requested_mode(self, mode: Mode) -> PiStatus:
        with self._lock:
            self._requested_mode = mode
            if mode in {Mode.FACE, Mode.AUDIO}:
                self._last_single_mode = mode
            self._active_mode = self._resolve_active_mode(mode, self._forced_mode)
            return self._snapshot_unlocked()

    def set_server_connected(self, available: bool) -> PiStatus:
        with self._lock:
            self._server_connected = available
            self._active_mode = self._resolve_active_mode(self._requested_mode, self._forced_mode)
            return self._snapshot_unlocked()

    def set_launcher(self, launcher: str | None) -> PiStatus:
        with self._lock:
            self._launcher = launcher.strip() if launcher else None
            return self._snapshot_unlocked()

    def _resolve_active_mode(self, requested_mode: Mode, forced_mode: Mode) -> Mode:
        if forced_mode is not Mode.AUTO:
            return forced_mode
        if self._server_connected and requested_mode in {Mode.FACE, Mode.AUDIO, Mode.BOTH}:
            return Mode.BOTH
        if requested_mode is Mode.BOTH:
            return self._last_single_mode
        return requested_mode

    def _snapshot_unlocked(self) -> PiStatus:
        return PiStatus(
            requested_mode=self._requested_mode.value,
            active_mode=self._active_mode.value,
            display_background=self._display_background,
            server_connected=self._server_connected,
            launcher=self._launcher,
        )


def serialize_status(status: PiStatus) -> dict[str, object]:
    return asdict(status)
