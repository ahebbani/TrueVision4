from __future__ import annotations

from fastapi.testclient import TestClient

from truevision_pi.main import create_app


def test_controller_mode_and_launcher_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUEVISION_FORCE_MODE", "auto")
    monkeypatch.setenv("TRUEVISION_SERVER_URL", "http://example.local:8008")

    with TestClient(create_app()) as client:
        response = client.post("/api/mode", json={"mode": "face"})
        assert response.status_code == 200
        assert response.json()["active_mode"] == "both"

        launcher = client.post("/api/launchers/open", json={"target": "database"})
        assert launcher.status_code == 200
        assert launcher.json()["launcher"] == "database"

        status = client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["server_connected"] is True


def test_controller_persists_faces_and_notes(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    with TestClient(create_app()) as client:
        note = client.post("/api/notes", json={"content": "Buy milk"})
        assert note.status_code == 200
        note_id = note.json()["note"]["id"]

        complete = client.post(f"/api/notes/{note_id}/done")
        assert complete.status_code == 200
        assert complete.json()["note"]["is_done"] is True

        face = client.post("/api/faces", json={"name": "John Doe"})
        assert face.status_code == 200
        assert face.json()["face"]["name"] == "John Doe"

        faces = client.get("/api/faces")
        assert faces.status_code == 200
        assert len(faces.json()["faces"]) == 1

        page = client.get("/")
        assert page.status_code == 200
        assert "TrueVision Controller" in page.text