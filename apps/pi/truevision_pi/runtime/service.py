from __future__ import annotations

from datetime import datetime, timezone
import json
from logging import Logger
from pathlib import Path
from threading import Event, Lock, Thread
import time
from typing import Any
from uuid import uuid4

from PIL import Image

from truevision_pi.audio.forwarder import AudioForwarder
from truevision_pi.audio.live_captioner import LiveCaptioner
from truevision_pi.audio.recorder import ESP32SerialRecorder
from truevision_pi.audio.serial_receiver import get_shared_receiver
from truevision_pi.audio.server_connection import ServerConnection
from truevision_pi.audio.transcriber import build_transcriber
from truevision_pi.faces.presence import PresenceTracker
from truevision_pi.faces.recognizer import FaceRecognizer
from truevision_pi.launchers.browser_launcher import BrowserLauncher
from truevision_pi.runtime.camera import CameraFrame, FrameSource, build_frame_source
from truevision_pi.runtime.hud import render_hud
from truevision_shared.config import AppConfig, DisplayBackground
from truevision_shared.pi_state import PiRuntimeState, serialize_status
from truevision_shared.store import PiStore, serialize_face
from truevision_server.summarization import summarize_one_sentence


class ActiveSession:
    def __init__(self, *, session_key: str, meeting_id: int, person_id: int | None, person_name: str | None, audio_path: str | None) -> None:
        self.session_key = session_key
        self.meeting_id = meeting_id
        self.person_id = person_id
        self.person_name = person_name
        self.audio_path = audio_path


class WindowRenderer:
    def __init__(self, logger: Logger) -> None:
        self._logger = logger
        self._cv2 = None
        if not self._initialize_backend():
            self._cv2 = None

    @property
    def available(self) -> bool:
        return self._cv2 is not None

    def show(self, image: Image.Image) -> None:
        if self._cv2 is None:
            return
        try:  # pragma: no cover - optional runtime path
            import numpy as np  # type: ignore
        except Exception as exc:  # pragma: no cover - optional runtime path
            self._logger.warning("numpy unavailable for window rendering", extra={"error": str(exc)})
            self._cv2 = None
            return

        frame = np.array(image.convert("RGB"))[:, :, ::-1]
        window_name = "TrueVision HUD"
        self._cv2.namedWindow(window_name, self._cv2.WINDOW_NORMAL)
        try:
            self._cv2.setWindowProperty(window_name, self._cv2.WND_PROP_FULLSCREEN, self._cv2.WINDOW_FULLSCREEN)
        except Exception:
            pass
        self._cv2.imshow(window_name, frame)
        self._cv2.waitKey(1)

    def close(self) -> None:
        if self._cv2 is not None:  # pragma: no cover - optional runtime path
            self._cv2.destroyAllWindows()

    def _initialize_backend(self) -> bool:
        try:  # pragma: no cover - depends on optional cv2 install
            import cv2  # type: ignore
        except Exception as exc:
            self._logger.warning("OpenCV window rendering unavailable", extra={"error": str(exc)})
            return False
        self._cv2 = cv2
        return True


class PiRuntimeService:
    def __init__(
        self,
        *,
        config: AppConfig,
        state: PiRuntimeState,
        store: PiStore,
        logger: Logger,
    ) -> None:
        self._config = config
        self._state = state
        self._store = store
        self._logger = logger
        self._frame_source: FrameSource = build_frame_source(config, logger)
        self._window = WindowRenderer(logger) if config.window_enabled else None
        self._receiver = get_shared_receiver(config, logger)
        self._recorder = ESP32SerialRecorder(config, self._receiver, logger)
        self._transcriber = build_transcriber(config, logger)
        self._captioner = LiveCaptioner(config, self._recorder, self._transcriber, logger)
        self._server_connection = ServerConnection(config, logger)
        self._forwarder = AudioForwarder(config, self._server_connection, self._receiver, self._captioner, logger)
        self._recognizer = FaceRecognizer(config, store, logger)
        self._presence = PresenceTracker(grace_period_sec=config.meeting_absence_grace_sec)
        self._launcher = BrowserLauncher(config, logger)
        self._lock = Lock()
        self._render_count = 0
        self._started = False
        self._last_status: dict[str, Any] = self._build_status(snapshot_ready=False)
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._audio_only_session: ActiveSession | None = None
        self._person_sessions: dict[int, ActiveSession] = {}
        self._latest_detections: list[dict[str, Any]] = []
        self._toast_text: str | None = None
        self._last_mode: str | None = None

        self._receiver.register_mode_callback(self._state.set_requested_mode)

    def start(self) -> None:
        if self._started:
            return
        self._logger.info("starting pi runtime service")
        self._stop_event.clear()
        self._receiver.start()
        self._server_connection.start()
        self.render_once()
        self._thread = Thread(target=self._run_loop, name="truevision-pi-runtime", daemon=True)
        self._thread.start()
        self._started = True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._shutdown_sessions()
        self._forwarder.close()
        self._server_connection.stop()
        self._receiver.stop()
        self._frame_source.stop()
        self._launcher.close()
        if self._window is not None:
            self._window.close()
        self._started = False

    def render_once(self) -> dict[str, Any]:
        self._state.set_server_connected(self._server_connection.is_available)
        state = serialize_status(self._state.snapshot())
        notes = self._store.list_notes(active_only=True)[:3]
        background_frame: CameraFrame | None = None
        camera_frame: CameraFrame | None = None

        if self._needs_camera_frame(state):
            try:
                camera_frame = self._frame_source.capture()
            except Exception as exc:
                self._logger.warning("camera capture failed; falling back to black background", extra={"error": str(exc)})

        if state["display_background"] == DisplayBackground.CAMERA.value and camera_frame is not None:
            background_frame = camera_frame

        detections = self._recognizer.recognize(camera_frame.image) if camera_frame and state["active_mode"] in {"face", "both"} else []
        self._latest_detections = [self._recognizer.serialize_detection(detection) for detection in detections]
        self._handle_mode_and_sessions(state, detections)
        self._forwarder.pump_audio()
        caption_text = self._captioner.update()

        enriched_state = {
            **state,
            "detected_faces": self._latest_detections,
            "detected_face_count": len(self._latest_detections),
            "caption_text": caption_text,
            "toast_text": self._toast_text,
            "audio_buffer_duration_sec": round(self._receiver.duration_seconds(), 2),
            "active_session_count": len(self._person_sessions) + (1 if self._audio_only_session else 0),
        }

        frame = render_hud(
            width=self._config.frame_width,
            height=self._config.frame_height,
            display_background=state["display_background"],
            camera_backend=(background_frame.backend if background_frame else self._frame_source.backend_name),
            camera_simulated=(background_frame.simulated if background_frame else self._frame_source.simulated),
            runtime_status=enriched_state,
            notes=notes,
            render_count=self._render_count + 1,
            background_image=background_frame.image if background_frame else None,
        )

        self._config.runtime_snapshot_dir.mkdir(parents=True, exist_ok=True)
        frame.save(self._config.runtime_snapshot_path, format="JPEG", quality=88)
        self._render_count += 1
        status = self._build_status(
            snapshot_ready=True,
            camera_backend=(background_frame.backend if background_frame else self._frame_source.backend_name),
            camera_simulated=(background_frame.simulated if background_frame else self._frame_source.simulated),
            active_notes=len(notes),
            known_faces=len(self._store.list_faces()),
            detected_faces=self._latest_detections,
            caption_text=caption_text,
            active_session_count=len(self._person_sessions) + (1 if self._audio_only_session else 0),
            toast_text=self._toast_text,
            receiver_stats=self._receiver.stats(),
        )
        self._config.runtime_metadata_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
        if self._window is not None:
            self._window.show(frame)

        with self._lock:
            self._last_status = status

        return status

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last_status)

    def open_launcher(self, target: str) -> dict[str, Any]:
        self._launcher.open(target)
        snapshot = self._state.set_launcher(target)
        self._toast_text = f"Opened: {target}"
        return serialize_status(snapshot)

    def close_launcher(self) -> dict[str, Any]:
        self._launcher.close()
        snapshot = self._state.set_launcher(None)
        self._toast_text = "Closed launcher"
        return serialize_status(snapshot)

    def enroll_face(self, name: str):
        frame = self._frame_source.capture()
        face = self._recognizer.enroll_largest_face(name, frame.image)
        self._toast_text = f"Saved: {name}"
        return face

    def checkpoints(self) -> list[dict[str, str]]:
        status = self.status()
        return self._checkpoints_for_status(status)

    def _checkpoints_for_status(self, status: dict[str, Any]) -> list[dict[str, str]]:
        checkpoints = [
            {
                "name": "database",
                "status": "pass" if Path(status["db_path"]).exists() else "fail",
                "detail": status["db_path"],
            },
            {
                "name": "snapshot_pipeline",
                "status": "pass" if status["snapshot_ready"] else "fail",
                "detail": status["snapshot_path"],
            },
            {
                "name": "camera_background",
                "status": self._camera_checkpoint_status(status),
                "detail": f"background={status['display_background']} backend={status['camera_backend']} simulated={status['camera_simulated']}",
            },
            {
                "name": "audio_pipeline",
                "status": "pass" if status["audio_buffer_duration_sec"] > 0 else "warn",
                "detail": f"buffer_sec={status['audio_buffer_duration_sec']} backend={status['receiver_stats']['backend']}",
            },
            {
                "name": "face_pipeline",
                "status": "pass" if status["known_face_count"] >= 0 and status["detected_face_count"] >= 0 else "fail",
                "detail": f"known={status['known_face_count']} detected={status['detected_face_count']}",
            },
            {
                "name": "display_window",
                "status": "pass"
                if status["window_requested"] and status["window_active"]
                else "warn"
                if status["window_requested"]
                else "pass",
                "detail": f"requested={status['window_requested']} active={status['window_active']}",
            },
        ]
        return checkpoints

    def _build_status(
        self,
        *,
        snapshot_ready: bool,
        camera_backend: str | None = None,
        camera_simulated: bool | None = None,
        active_notes: int = 0,
        known_faces: int = 0,
        detected_faces: list[dict[str, Any]] | None = None,
        caption_text: str = "",
        active_session_count: int = 0,
        toast_text: str | None = None,
        receiver_stats: dict[str, float | int | str] | None = None,
    ) -> dict[str, Any]:
        state = serialize_status(self._state.snapshot())
        now = datetime.now(timezone.utc).isoformat()
        status: dict[str, Any] = {
            **state,
            "db_path": str(self._config.pi_db_path),
            "snapshot_ready": snapshot_ready,
            "snapshot_path": str(self._config.runtime_snapshot_path),
            "metadata_path": str(self._config.runtime_metadata_path),
            "camera_backend": camera_backend or self._frame_source.backend_name,
            "camera_simulated": self._frame_source.simulated if camera_simulated is None else camera_simulated,
            "window_requested": self._config.window_enabled,
            "window_active": bool(self._window and self._window.available),
            "render_count": self._render_count,
            "last_rendered_at": now,
            "active_note_count": active_notes,
            "known_face_count": known_faces,
            "detected_face_count": len(detected_faces or []),
            "detected_faces": detected_faces or [],
            "caption_text": caption_text,
            "active_session_count": active_session_count,
            "audio_buffer_duration_sec": round(self._receiver.duration_seconds(), 2),
            "toast_text": toast_text,
            "receiver_stats": receiver_stats or self._receiver.stats(),
        }
        status["checkpoints"] = self._checkpoints_for_status(status) if snapshot_ready else []
        return status

    def _camera_checkpoint_status(self, status: dict[str, Any]) -> str:
        if status["display_background"] != DisplayBackground.CAMERA.value:
            return "pass"
        if not status["camera_simulated"]:
            return "pass"
        return "warn"

    def _needs_camera_frame(self, state: dict[str, Any]) -> bool:
        return state["display_background"] == DisplayBackground.CAMERA.value or state["active_mode"] in {"face", "both"}

    def _handle_mode_and_sessions(self, state: dict[str, Any], detections) -> None:
        active_mode = state["active_mode"]
        if active_mode != self._last_mode:
            self._toast_text = f"Mode: {active_mode.upper()}"
            self._last_mode = active_mode

        if active_mode == "audio":
            for event in self._presence.clear():
                self._stop_person_session(event.face_id)
            self._ensure_audio_only_session()
            return

        if active_mode == "both":
            self._ensure_audio_only_session(stop_only=True)
            for event in self._presence.update(detections):
                if event.kind == "present" and event.detection is not None:
                    self._start_person_session(event.detection)
                elif event.kind == "absent":
                    self._stop_person_session(event.face_id)
            return

        self._ensure_audio_only_session(stop_only=True)
        for event in self._presence.clear():
            self._stop_person_session(event.face_id)

    def _ensure_audio_only_session(self, *, stop_only: bool = False) -> None:
        if stop_only:
            if self._audio_only_session is not None:
                self._finalize_session(self._audio_only_session)
                self._audio_only_session = None
            return
        if self._audio_only_session is not None:
            return
        session_key = f"audio-{uuid4().hex[:8]}"
        wav_path = self._recorder.start(self._config.audio_dir, "audio")
        meeting = self._store.create_meeting(person_id=None, audio_path=str(wav_path), session_key=session_key)
        self._audio_only_session = ActiveSession(
            session_key=session_key,
            meeting_id=meeting.id,
            person_id=None,
            person_name=None,
            audio_path=str(wav_path),
        )
        self._captioner.start_session(session_key, meeting.id)
        if self._server_connection.is_available:
            self._forwarder.start_session(session_key=session_key, person_id=None, meeting_id=meeting.id, person_name=None)

    def _start_person_session(self, detection) -> None:
        if detection.face_id is None or detection.face_id in self._person_sessions:
            return
        self._store.mark_face_seen(detection.face_id)
        session_key = f"face-{detection.face_id}-{uuid4().hex[:6]}"
        wav_path = self._recorder.start(self._config.audio_dir, f"face-{detection.face_id}")
        meeting = self._store.create_meeting(
            person_id=detection.face_id,
            audio_path=str(wav_path),
            session_key=session_key,
        )
        self._person_sessions[detection.face_id] = ActiveSession(
            session_key=session_key,
            meeting_id=meeting.id,
            person_id=detection.face_id,
            person_name=detection.name,
            audio_path=str(wav_path),
        )
        self._captioner.start_session(session_key, meeting.id)
        if self._server_connection.is_available:
            self._forwarder.start_session(
                session_key=session_key,
                person_id=detection.face_id,
                meeting_id=meeting.id,
                person_name=detection.name,
            )

    def _stop_person_session(self, face_id: int) -> None:
        session = self._person_sessions.pop(face_id, None)
        if session is not None:
            self._finalize_session(session)

    def _finalize_session(self, session: ActiveSession) -> None:
        self._captioner.stop_session(session.session_key)
        previous_summary = self._store.get_latest_summary(session.person_id) if session.person_id is not None else None
        remote_result = None
        if self._server_connection.is_available:
            remote_result = self._forwarder.end_session(
                session_key=session.session_key,
                previous_summary=previous_summary,
                person_name=session.person_name,
                max_chars=140,
            )
        audio_path = self._recorder.stop() or Path(session.audio_path) if session.audio_path else None
        transcript = ""
        summary = ""
        source_language = None
        if remote_result is not None:
            transcript = str(remote_result.get("transcript", ""))
            summary = str(remote_result.get("summary", ""))
            source_language = remote_result.get("source_language") if isinstance(remote_result.get("source_language"), str) else None
        elif audio_path is not None:
            result = self._transcriber.transcribe(Path(audio_path))
            transcript = result.text
            source_language = result.source_language
            summary = self._server_connection.summarize(
                transcript=transcript,
                previous_summary=previous_summary,
                person_name=session.person_name,
                max_chars=140,
            ) or summarize_one_sentence(
                transcript,
                previous_summary=previous_summary,
                person_name=session.person_name,
                max_chars=140,
            )
        self._store.finalize_meeting(
            session.meeting_id,
            transcript=transcript,
            summary=summary,
            audio_path=str(audio_path) if audio_path else session.audio_path,
            source_language=source_language,
        )
        self._toast_text = summary[:58] if summary else "Session saved"
        self._handle_command_intents(transcript, session)

    def _handle_command_intents(self, transcript: str, session: ActiveSession) -> None:
        normalized = transcript.lower().strip()
        if not normalized:
            return
        if "assistant" not in normalized and "truevision" not in normalized:
            return
        from truevision_server.telegram import extract_command_text

        command = extract_command_text(transcript)
        lowered = command.lower()
        if any(token in lowered for token in ("remind", "note", "remember")) and "face" not in lowered:
            self._store.add_note(command)
            self._toast_text = f"Reminder saved: {command[:36]}"
            return
        if "telegram" in lowered or lowered.startswith("send"):
            result = self._server_connection.send_command("telegram_llm", command=transcript)
            if result is not None:
                self._toast_text = "Telegram sent"
            else:
                self._toast_text = "Telegram unavailable"

    def _shutdown_sessions(self) -> None:
        if self._audio_only_session is not None:
            self._finalize_session(self._audio_only_session)
            self._audio_only_session = None
        for face_id in list(self._person_sessions):
            self._stop_person_session(face_id)

    def _run_loop(self) -> None:
        interval = 1 / self._config.runtime_fps
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                self.render_once()
            except Exception as exc:  # pragma: no cover - defensive background path
                self._logger.exception("runtime render failed", exc_info=exc)
            elapsed = time.monotonic() - started
            self._stop_event.wait(max(0.01, interval - elapsed))
