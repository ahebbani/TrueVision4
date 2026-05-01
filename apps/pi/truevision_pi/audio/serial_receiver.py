from __future__ import annotations

from collections.abc import Callable
import math
from pathlib import Path
import threading
import time
import wave

import numpy as np

from truevision_shared.config import AppConfig, AudioBackend, Mode
from truevision_shared.protocol import PacketType, SerialFrameParser, build_frame


class AudioRingBuffer:
    def __init__(self, *, sample_rate: int, channels: int, capacity_sec: int = 60) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._capacity_bytes = sample_rate * channels * 2 * capacity_sec
        self._buffer = bytearray()
        self._cursor = 0
        self._lock = threading.Lock()

    def append(self, pcm_bytes: bytes) -> None:
        with self._lock:
            self._buffer.extend(pcm_bytes)
            overflow = len(self._buffer) - self._capacity_bytes
            if overflow > 0:
                del self._buffer[:overflow]
                self._cursor += overflow

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    def get_all(self) -> bytes:
        with self._lock:
            return bytes(self._buffer)

    def get_last_n_seconds(self, seconds: float) -> bytes:
        if seconds <= 0:
            return b""
        bytes_needed = int(self._sample_rate * self._channels * 2 * seconds)
        with self._lock:
            return bytes(self._buffer[-bytes_needed:])

    def read_since(self, cursor: int) -> tuple[int, bytes]:
        with self._lock:
            base_cursor = self._cursor
            if cursor < base_cursor:
                cursor = base_cursor
            start = cursor - base_cursor
            payload = bytes(self._buffer[start:])
            return base_cursor + len(self._buffer), payload

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            byte_count = len(self._buffer)
        return byte_count / (self._sample_rate * self._channels * 2)


class ESP32SerialReceiver:
    def __init__(self, config: AppConfig, logger) -> None:
        self._config = config
        self._logger = logger
        self._parser = SerialFrameParser()
        self._ring_buffer = AudioRingBuffer(
            sample_rate=config.audio_sample_rate,
            channels=config.audio_channels,
        )
        self._mode_callbacks: list[Callable[[Mode], None]] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._mode = Mode.FACE
        self._stats_lock = threading.Lock()
        self._audio_packets = 0
        self._checksum_errors = 0
        self._mock_phase = 0.0
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="truevision-serial-receiver", daemon=True)
        self._thread.start()
        self._started = True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._started = False

    def register_mode_callback(self, callback: Callable[[Mode], None]) -> None:
        self._mode_callbacks.append(callback)

    def feed_raw_bytes(self, payload: bytes) -> None:
        for frame in self._parser.feed(payload):
            if frame.packet_type is PacketType.AUDIO_DATA:
                self._ring_buffer.append(frame.data)
                with self._stats_lock:
                    self._audio_packets += 1
            elif frame.packet_type is PacketType.MODE_CHANGE and frame.data:
                requested_mode = Mode.AUDIO if frame.data[0] == 0x00 else Mode.FACE
                self._mode = requested_mode
                for callback in self._mode_callbacks:
                    callback(requested_mode)

    def clear_buffer(self) -> None:
        self._ring_buffer.clear()

    def get_all_audio(self) -> bytes:
        return self._ring_buffer.get_all()

    def get_last_n_seconds(self, seconds: float) -> bytes:
        return self._ring_buffer.get_last_n_seconds(seconds)

    def read_audio_since(self, cursor: int) -> tuple[int, bytes]:
        return self._ring_buffer.read_since(cursor)

    def duration_seconds(self) -> float:
        return self._ring_buffer.duration_seconds

    def write_to_wav(self, output_path: Path, pcm_bytes: bytes) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(self._config.audio_channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._config.audio_sample_rate)
            wav_file.writeframes(pcm_bytes)
        return output_path

    def stats(self) -> dict[str, float | int | str]:
        with self._stats_lock:
            return {
                "backend": self._config.audio_backend.value,
                "mode": self._mode.value,
                "audio_packets": self._audio_packets,
                "checksum_errors": self._checksum_errors,
                "buffer_duration_sec": round(self._ring_buffer.duration_seconds, 3),
            }

    def _run(self) -> None:
        if self._config.audio_backend in {AudioBackend.MOCK, AudioBackend.AUTO}:
            self._logger.info("starting mock audio receiver")
            self._run_mock_audio()
            return

        try:
            import serial  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency path
            self._logger.warning("pyserial unavailable; falling back to mock audio", extra={"error": str(exc)})
            self._run_mock_audio()
            return

        backoff = 1.0
        while not self._stop_event.is_set():  # pragma: no cover - hardware path
            try:
                with serial.Serial(self._config.serial_port, self._config.serial_baud_rate, timeout=0.1) as serial_port:
                    self._logger.info("serial receiver connected", extra={"port": self._config.serial_port})
                    backoff = 1.0
                    while not self._stop_event.is_set():
                        payload = serial_port.read(4096)
                        if payload:
                            self.feed_raw_bytes(payload)
            except Exception as exc:
                self._logger.warning("serial receiver disconnected", extra={"error": str(exc)})
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, 8.0)

    def _run_mock_audio(self) -> None:
        sample_rate = self._config.audio_sample_rate
        chunk = self._config.audio_chunk_samples
        self._ring_buffer.clear()
        for callback in self._mode_callbacks:
            callback(self._mode)

        while not self._stop_event.is_set():
            time_axis = np.arange(chunk, dtype=np.float32)
            wave_chunk = 0.12 * np.sin(2 * math.pi * (self._mock_phase + time_axis) * 220.0 / sample_rate)
            self._mock_phase += chunk
            pcm = np.clip(wave_chunk * 32767, -32768, 32767).astype(np.int16).tobytes()
            self.feed_raw_bytes(build_frame(PacketType.AUDIO_DATA, pcm))
            time.sleep(chunk / sample_rate)


_RECEIVERS: dict[str, ESP32SerialReceiver] = {}


def get_shared_receiver(config: AppConfig, logger) -> ESP32SerialReceiver:
    key = f"{config.audio_backend.value}:{config.serial_port}"
    receiver = _RECEIVERS.get(key)
    if receiver is None:
        receiver = ESP32SerialReceiver(config, logger)
        _RECEIVERS[key] = receiver
    return receiver
