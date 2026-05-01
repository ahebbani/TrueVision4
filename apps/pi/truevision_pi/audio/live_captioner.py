from __future__ import annotations

import time

from truevision_pi.audio.recorder import ESP32SerialRecorder
from truevision_pi.audio.transcriber import FallbackTranscriber
from truevision_shared.config import AppConfig


class LiveCaptioner:
    def __init__(
        self,
        config: AppConfig,
        recorder: ESP32SerialRecorder,
        transcriber: FallbackTranscriber,
        logger,
    ) -> None:
        self._config = config
        self._recorder = recorder
        self._transcriber = transcriber
        self._logger = logger
        self._session_key: str | None = None
        self._meeting_id: int | None = None
        self._caption_text = ""
        self._last_update = 0.0

    def start_session(self, session_key: str, meeting_id: int | None) -> None:
        self._session_key = session_key
        self._meeting_id = meeting_id
        self._caption_text = ""
        self._last_update = 0.0

    def stop_session(self, session_key: str) -> None:
        if self._session_key == session_key:
            self._session_key = None
            self._meeting_id = None

    def update(self, *, language: str | None = None) -> str:
        if self._session_key is None:
            self._caption_text = ""
            return self._caption_text
        now = time.monotonic()
        if now - self._last_update < self._config.caption_interval_sec:
            return self._caption_text
        self._last_update = now
        wav_path = self._recorder.flush_to_wav(self._config.caption_window_sec)
        if wav_path is None:
            return self._caption_text
        result = self._transcriber.transcribe_live(wav_path, language=language)
        self._caption_text = result.text
        return self._caption_text

    def set_remote_caption(self, text: str) -> None:
        self._caption_text = text

    def latest_caption(self) -> str:
        return self._caption_text
