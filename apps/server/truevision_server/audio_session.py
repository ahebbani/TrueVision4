from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import threading
import wave

from truevision_shared.protocol import caption_message, result_message
from truevision_shared.store import JobRecord, ServerStore
from truevision_server.summarization import summarize_one_sentence


@dataclass(slots=True)
class ServerAudioSession:
    session_key: str
    meeting_id: int | None
    person_id: int | None
    person_name: str | None
    source_language: str | None = None
    audio_bytes: bytearray | None = None
    caption_count: int = 0

    def __post_init__(self) -> None:
        if self.audio_bytes is None:
            self.audio_bytes = bytearray()


class AudioSessionProcessor:
    def __init__(self, config, logger, store: ServerStore) -> None:
        self._config = config
        self._logger = logger
        self._store = store
        self._sessions: dict[str, ServerAudioSession] = {}
        self._lock = threading.Lock()

    def start_session(self, payload: dict[str, object]) -> ServerAudioSession:
        session = ServerAudioSession(
            session_key=str(payload.get("session_key", "session")),
            meeting_id=int(payload["meeting_id"]) if payload.get("meeting_id") is not None else None,
            person_id=int(payload["person_id"]) if payload.get("person_id") is not None else None,
            person_name=str(payload.get("person_name")) if payload.get("person_name") else None,
            source_language=str(payload.get("source_language")) if payload.get("source_language") else None,
        )
        with self._lock:
            self._sessions[session.session_key] = session
        return session

    def append_audio(self, session_key: str, payload: bytes) -> dict[str, object] | None:
        session = self._sessions.get(session_key)
        if session is None:
            return None
        session.audio_bytes.extend(payload)
        session.caption_count += 1
        duration = self._duration_for_bytes(session.audio_bytes)
        text = f"Live caption {duration:.1f}s"
        if session.caption_count % 4 == 0 or duration >= self._config.caption_window_sec:
            return caption_message(text=text, session_key=session.session_key, source_language=session.source_language)
        return None

    def finalize_session(self, payload: dict[str, object]) -> dict[str, object]:
        session_key = str(payload.get("session_key", "session"))
        session = self._sessions.pop(session_key, None)
        if session is None:
            return result_message(session_key=session_key, meeting_id=None, transcript="", summary="")

        audio_path = self._write_temp_wav(session)
        transcript = self._transcribe(audio_path, source_language=session.source_language)
        summary = summarize_one_sentence(
            transcript,
            previous_summary=str(payload.get("previous_summary")) if payload.get("previous_summary") else None,
            person_name=session.person_name,
            max_chars=int(payload.get("max_chars", 140)),
        )

        if session.meeting_id is not None:
            existing = self._store.get_job_by_meeting(session.meeting_id)
            if existing is None:
                existing = self._store.create_job(meeting_id=session.meeting_id, audio_path=str(audio_path))
            self._store.update_job(
                existing.id,
                status="done",
                transcript=transcript,
                summary=summary,
            )

        return result_message(
            session_key=session.session_key,
            meeting_id=session.meeting_id,
            transcript=transcript,
            summary=summary,
        )

    def enqueue_backfill(self, *, meeting_id: int, audio_path: str) -> JobRecord:
        return self._store.create_job(meeting_id=meeting_id, audio_path=audio_path)

    def process_queued_jobs(self) -> list[JobRecord]:
        processed: list[JobRecord] = []
        for job in self._store.list_jobs(status="queued"):
            self._store.update_job(job.id, status="processing")
            transcript = self._transcribe(Path(job.audio_path), source_language=None)
            summary = summarize_one_sentence(transcript, max_chars=140)
            updated = self._store.update_job(job.id, status="done", transcript=transcript, summary=summary)
            if updated is not None:
                processed.append(updated)
        return processed

    def _write_temp_wav(self, session: ServerAudioSession) -> Path:
        temp_path = Path(tempfile.gettempdir()) / f"truevision-server-{session.session_key}.wav"
        with wave.open(str(temp_path), "wb") as wav_file:
            wav_file.setnchannels(self._config.audio_channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._config.audio_sample_rate)
            wav_file.writeframes(bytes(session.audio_bytes))
        return temp_path

    def _transcribe(self, audio_path: Path, *, source_language: str | None) -> str:
        try:
            with wave.open(str(audio_path), "rb") as wav_file:
                duration = wav_file.getnframes() / (wav_file.getframerate() or 1)
        except (FileNotFoundError, wave.Error):
            duration = 0.0
        if source_language and source_language != "en":
            return f"Translated {source_language} meeting lasting {duration:.1f} seconds."
        return f"Server transcript for {duration:.1f} seconds of audio."

    def _duration_for_bytes(self, payload: bytes | bytearray) -> float:
        return len(payload) / (self._config.audio_sample_rate * self._config.audio_channels * 2)


class BackfillWorker:
    def __init__(self, processor: AudioSessionProcessor, interval_sec: float = 5.0) -> None:
        self._processor = processor
        self._interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="truevision-backfill-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._processor.process_queued_jobs()
            self._stop_event.wait(self._interval_sec)
