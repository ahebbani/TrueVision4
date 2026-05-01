from __future__ import annotations

import time

from truevision_pi.runtime.service import PiRuntimeService
from truevision_pi.audio.transcriber import TranscriptResult
from truevision_shared.config import Mode, RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.logging_utils import configure_logging
from truevision_shared.pi_state import PiRuntimeState
from truevision_shared.store import PiStore


def test_audio_mode_creates_meeting(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUEVISION_CAMERA_BACKEND", "mock")
    monkeypatch.setenv("TRUEVISION_AUDIO_BACKEND", "mock")
    monkeypatch.setenv("TRUEVISION_ENABLE_WINDOW", "0")
    config = load_config(RuntimeRole.PI, base_dir=tmp_path)
    initialize_pi_database(config.pi_db_path)
    logger = configure_logging(config.log_dir, logger_name="truevision-pi-session-test")
    state = PiRuntimeState(config)
    store = PiStore(config.pi_db_path)

    runtime = PiRuntimeService(config=config, state=state, store=store, logger=logger)
    runtime.start()
    state.set_requested_mode(Mode.AUDIO)
    time.sleep(0.8)
    runtime.render_once()
    state.set_requested_mode(Mode.FACE)
    runtime.render_once()
    runtime.stop()

    meetings = store.list_meetings(limit=5)
    assert meetings
    assert meetings[0].status == "done"


def test_enroll_face_updates_runtime(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUEVISION_CAMERA_BACKEND", "mock")
    monkeypatch.setenv("TRUEVISION_AUDIO_BACKEND", "mock")
    monkeypatch.setenv("TRUEVISION_ENABLE_WINDOW", "0")
    config = load_config(RuntimeRole.PI, base_dir=tmp_path)
    initialize_pi_database(config.pi_db_path)
    logger = configure_logging(config.log_dir, logger_name="truevision-pi-enroll-test")
    state = PiRuntimeState(config)
    store = PiStore(config.pi_db_path)
    runtime = PiRuntimeService(config=config, state=state, store=store, logger=logger)

    face = runtime.enroll_face("Morgan")
    state.set_requested_mode(Mode.FACE)
    status = runtime.render_once()

    assert face.name == "Morgan"
    assert status["known_face_count"] >= 1


def test_session_finalization_does_not_block_render_loop(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUEVISION_CAMERA_BACKEND", "mock")
    monkeypatch.setenv("TRUEVISION_AUDIO_BACKEND", "mock")
    monkeypatch.setenv("TRUEVISION_ENABLE_WINDOW", "0")
    config = load_config(RuntimeRole.PI, base_dir=tmp_path)
    initialize_pi_database(config.pi_db_path)
    logger = configure_logging(config.log_dir, logger_name="truevision-pi-nonblocking-finalize-test")
    state = PiRuntimeState(config)
    store = PiStore(config.pi_db_path)

    runtime = PiRuntimeService(config=config, state=state, store=store, logger=logger)
    runtime.start()
    state.set_requested_mode(Mode.AUDIO)
    time.sleep(0.8)
    runtime.render_once()

    def slow_transcribe(_audio_path, *, language=None, task="transcribe"):
        time.sleep(0.4)
        return TranscriptResult(text="Background finalization complete.", source_language=language)

    monkeypatch.setattr(runtime._transcriber, "transcribe", slow_transcribe)

    start = time.monotonic()
    state.set_requested_mode(Mode.FACE)
    runtime.render_once()
    elapsed = time.monotonic() - start

    deadline = time.monotonic() + 2.0
    latest_meeting = None
    while time.monotonic() < deadline:
        meetings = store.list_meetings(limit=1)
        latest_meeting = meetings[0] if meetings else None
        if latest_meeting is not None and latest_meeting.status == "done":
            break
        time.sleep(0.05)

    runtime.stop()

    assert elapsed < 0.25
    assert latest_meeting is not None
    assert latest_meeting.status == "done"
