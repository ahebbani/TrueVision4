from __future__ import annotations

import io
import os
import tempfile
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from truevision_server.app import create_app


def test_server_websocket_and_backfill_flow() -> None:
    previous_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(Path(tmpdir))
        with TestClient(create_app()) as client:
            with client.websocket_connect("/ws/audio") as websocket:
                websocket.send_json({"type": "session_start", "session_key": "s1", "meeting_id": 1, "person_name": "Alex"})
                chunk = b"\x00\x00" * 4000
                for _ in range(4):
                    websocket.send_bytes(chunk)
                caption = websocket.receive_json()
                assert caption["type"] == "caption"
                websocket.send_json({"type": "session_end", "session_key": "s1", "person_name": "Alex", "max_chars": 80})
                result = websocket.receive_json()
                assert result["type"] == "result"
                assert result["meeting_id"] == 1

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\x00\x00" * 16000)

            uploaded = client.post("/api/meetings/9/audio", content=wav_buffer.getvalue())
            assert uploaded.status_code == 200
            triggered = client.post("/api/backfill/trigger")
            assert triggered.status_code == 200
            status = client.get("/api/meetings/9/status")
            assert status.status_code == 200
            assert status.json()["job"]["status"] == "done"
    os.chdir(previous_cwd)
