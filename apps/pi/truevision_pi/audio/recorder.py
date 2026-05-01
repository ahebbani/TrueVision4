from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from uuid import uuid4

from truevision_pi.audio.serial_receiver import ESP32SerialReceiver
from truevision_shared.config import AppConfig


@dataclass(slots=True)
class RecordingSession:
    wav_path: Path
    prefix: str


class ESP32SerialRecorder:
    def __init__(self, config: AppConfig, receiver: ESP32SerialReceiver, logger) -> None:
        self._config = config
        self._receiver = receiver
        self._logger = logger
        self._session: RecordingSession | None = None

    def start(self, directory: Path, prefix: str) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        self._receiver.clear_buffer()
        wav_path = directory / f"{prefix}-{uuid4().hex[:8]}.wav"
        self._session = RecordingSession(wav_path=wav_path, prefix=prefix)
        return wav_path

    def stop(self) -> Path | None:
        if self._session is None:
            return None
        pcm_bytes = self._receiver.get_all_audio()
        output_path = self._session.wav_path
        self._session = None
        if self._receiver.duration_seconds() < 0.5:
            self._logger.info("skipping wav write for short audio clip", extra={"path": str(output_path)})
            return output_path
        return self._receiver.write_to_wav(output_path, pcm_bytes)

    def flush_to_wav(self, seconds: float) -> Path | None:
        pcm_bytes = self._receiver.get_last_n_seconds(seconds)
        if len(pcm_bytes) < int(self._config.audio_sample_rate * self._config.audio_channels):
            return None
        temp_path = Path(tempfile.gettempdir()) / f"truevision-caption-{uuid4().hex[:8]}.wav"
        return self._receiver.write_to_wav(temp_path, pcm_bytes)
