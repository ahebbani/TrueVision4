from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave

from truevision_shared.config import AppConfig
from truevision_shared.protocol import format_caption


@dataclass(slots=True)
class TranscriptResult:
    text: str
    source_language: str | None = None
    translated: bool = False
    duration_seconds: float = 0.0


class FallbackTranscriber:
    def __init__(self, config: AppConfig, logger) -> None:
        self._config = config
        self._logger = logger

    def transcribe(self, audio_path: Path, *, language: str | None = None, task: str = "transcribe") -> TranscriptResult:
        duration = _wav_duration(audio_path)
        if duration <= 0:
            return TranscriptResult(text="", source_language=language, translated=(task == "translate"))

        source_language = language or "en"
        if task == "translate" and source_language != "en":
            text = f"Translated {source_language} speech lasting {duration:.1f} seconds."
            return TranscriptResult(
                text=format_caption(text, source_language),
                source_language=source_language,
                translated=True,
                duration_seconds=duration,
            )

        if duration < 1.0:
            text = "Short utterance captured."
        elif duration < 4.0:
            text = f"Conversation snippet lasting {duration:.1f} seconds."
        else:
            text = f"Conversation captured for {duration:.1f} seconds with stable audio."
        return TranscriptResult(text=text, source_language=source_language, duration_seconds=duration)

    def transcribe_live(self, audio_path: Path, *, language: str | None = None) -> TranscriptResult:
        result = self.transcribe(audio_path, language=language)
        if result.duration_seconds <= 0:
            return result
        live_text = f"Listening {result.duration_seconds:.1f}s"
        if language and language != "en":
            live_text = format_caption(live_text, language)
        return TranscriptResult(
            text=live_text,
            source_language=language or result.source_language,
            duration_seconds=result.duration_seconds,
        )


def build_transcriber(config: AppConfig, logger) -> FallbackTranscriber:
    try:  # pragma: no cover - optional runtime dependency
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        logger.info("using fallback transcriber", extra={"model": config.whisper_model})
        return FallbackTranscriber(config, logger)

    class FasterWhisperTranscriber(FallbackTranscriber):
        def __init__(self, config: AppConfig, logger) -> None:
            super().__init__(config, logger)
            device = config.whisper_device if config.whisper_device != "auto" else "cpu"
            self._model = WhisperModel(config.whisper_model, device=device, compute_type=config.whisper_compute_type)

        def transcribe(self, audio_path: Path, *, language: str | None = None, task: str = "transcribe") -> TranscriptResult:
            segments, info = self._model.transcribe(
                str(audio_path),
                beam_size=1,
                language=language,
                task=task,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
            return TranscriptResult(
                text=text,
                source_language=getattr(info, "language", language),
                translated=(task == "translate"),
                duration_seconds=_wav_duration(audio_path),
            )

        def transcribe_live(self, audio_path: Path, *, language: str | None = None) -> TranscriptResult:
            return self.transcribe(audio_path, language=language)

    logger.info("using faster-whisper transcriber", extra={"model": config.whisper_model})
    return FasterWhisperTranscriber(config, logger)


def _wav_duration(audio_path: Path) -> float:
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate() or 1
    except FileNotFoundError:
        return 0.0
    return frames / rate
