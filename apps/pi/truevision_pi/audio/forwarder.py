from __future__ import annotations

import json
from threading import Lock
import time

from websockets.sync.client import connect

from truevision_pi.audio.live_captioner import LiveCaptioner
from truevision_pi.audio.serial_receiver import ESP32SerialReceiver
from truevision_pi.audio.server_connection import ServerConnection
from truevision_shared.config import AppConfig
from truevision_shared.protocol import WebsocketMessageType, control_message, encode_json_message


class AudioForwarder:
    def __init__(
        self,
        config: AppConfig,
        server_connection: ServerConnection,
        receiver: ESP32SerialReceiver,
        captioner: LiveCaptioner,
        logger,
    ) -> None:
        self._config = config
        self._server_connection = server_connection
        self._receiver = receiver
        self._captioner = captioner
        self._logger = logger
        self._connection = None
        self._cursor = 0
        self._active_session_key: str | None = None
        self._results: dict[str, dict[str, object]] = {}
        self._lock = Lock()

    def start_session(self, *, session_key: str, person_id: int | None, meeting_id: int | None, person_name: str | None) -> None:
        if not self._ensure_connection():
            return
        with self._lock:
            self._active_session_key = session_key
            self._cursor = 0
            message = control_message(
                WebsocketMessageType.SESSION_START,
                session_key=session_key,
                person_id=person_id,
                meeting_id=meeting_id,
                person_name=person_name,
            )
            self._connection.send(encode_json_message(message))
        self.poll_messages()

    def pump_audio(self) -> None:
        with self._lock:
            if self._connection is None or self._active_session_key is None:
                return
            self._cursor, payload = self._receiver.read_audio_since(self._cursor)
            if payload:
                self._connection.send(payload)
        self.poll_messages()

    def end_session(
        self,
        *,
        session_key: str,
        previous_summary: str | None,
        person_name: str | None,
        max_chars: int,
    ) -> dict[str, object] | None:
        with self._lock:
            if self._connection is None:
                return None
            message = control_message(
                WebsocketMessageType.SESSION_END,
                session_key=session_key,
                previous_summary=previous_summary,
                person_name=person_name,
                max_chars=max_chars,
            )
            self._connection.send(encode_json_message(message))
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            self.poll_messages()
            with self._lock:
                result = self._results.pop(session_key, None)
            if result is not None:
                with self._lock:
                    if self._active_session_key == session_key:
                        self._active_session_key = None
                return result
            time.sleep(0.05)
        return None

    def poll_messages(self) -> None:
        while True:
            try:
                with self._lock:
                    if self._connection is None:
                        return
                    message = self._connection.recv(timeout=0)
            except TimeoutError:
                return
            except Exception as exc:
                self._logger.warning("audio forwarder disconnected", extra={"error": str(exc)})
                self.close()
                return
            if not isinstance(message, str):
                continue
            payload = json.loads(message)
            message_type = payload.get("type")
            if message_type == WebsocketMessageType.CAPTION.value:
                self._captioner.set_remote_caption(str(payload.get("text", "")))
            elif message_type == WebsocketMessageType.RESULT.value:
                session_key = str(payload.get("session_key", ""))
                with self._lock:
                    self._results[session_key] = payload

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception:
                    pass
                self._connection = None
            self._active_session_key = None

    def _ensure_connection(self) -> bool:
        with self._lock:
            if self._connection is not None:
                return True
        server_url = self._server_connection.server_url
        if not server_url or not self._server_connection.is_available:
            return False
        ws_url = server_url.rstrip("/")
        if ws_url.startswith("https://"):
            ws_url = "wss://" + ws_url[len("https://") :]
        elif ws_url.startswith("http://"):
            ws_url = "ws://" + ws_url[len("http://") :]
        ws_url += "/ws/audio"
        try:
            connection = connect(ws_url, open_timeout=self._config.server_connect_timeout_sec)
            with self._lock:
                self._connection = connection
            return True
        except Exception as exc:
            self._logger.warning("audio forwarder could not connect", extra={"error": str(exc), "url": ws_url})
            with self._lock:
                self._connection = None
            return False
