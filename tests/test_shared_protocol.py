from __future__ import annotations

from pathlib import Path

from truevision_shared.config import Mode, RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.pi_state import PiRuntimeState
from truevision_shared.protocol import PacketType, SerialFrameParser, build_frame, caption_message, format_caption
from truevision_shared.store import PiStore


def test_serial_frame_parser_round_trip() -> None:
    parser = SerialFrameParser()
    payload = build_frame(PacketType.MODE_CHANGE, b"\x00") + build_frame(PacketType.MARKER, b"\x01")
    frames = parser.feed(payload)
    assert [frame.packet_type for frame in frames] == [PacketType.MODE_CHANGE, PacketType.MARKER]


def test_pi_state_server_fallback(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TRUEVISION_SERVER_URL", "http://server.local:8008")
    config = load_config(RuntimeRole.PI, base_dir=tmp_path)
    state = PiRuntimeState(config)
    state.set_requested_mode(Mode.AUDIO)
    assert state.snapshot().active_mode == "both"
    state.set_server_connected(False)
    assert state.snapshot().active_mode == "audio"


def test_meeting_lifecycle_and_caption_format(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    config = load_config(RuntimeRole.PI, base_dir=tmp_path)
    initialize_pi_database(config.pi_db_path)
    store = PiStore(config.pi_db_path)
    face = store.add_face("Jordan", embedding=b"1234", quality=0.9)
    meeting = store.create_meeting(person_id=face.id, audio_path=str(Path(tmp_path) / "demo.wav"), session_key="s1")
    finished = store.finalize_meeting(meeting.id, transcript="hello", summary="Jordan: hello")
    assert finished is not None
    assert finished.status == "done"
    assert format_caption("hello", "es") == "(Spanish) hello"
    assert caption_message("hello", "s1", "es")["text"] == "(Spanish) hello"
