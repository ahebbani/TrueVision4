from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from truevision_pi.main import create_app
from truevision_pi.runtime.service import PiRuntimeService
from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.logging_utils import configure_logging
from truevision_shared.pi_state import PiRuntimeState
from truevision_shared.store import PiStore


def test_runtime_service_renders_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUEVISION_CAMERA_BACKEND", "mock")
    monkeypatch.setenv("TRUEVISION_DISPLAY_BACKGROUND", "camera")
    monkeypatch.setenv("TRUEVISION_ENABLE_WINDOW", "0")

    config = load_config(RuntimeRole.PI, base_dir=tmp_path)
    initialize_pi_database(config.pi_db_path)
    logger = configure_logging(config.log_dir, logger_name="truevision-pi-runtime-test")
    state = PiRuntimeState(config)
    store = PiStore(config.pi_db_path)
    store.add_note("Buy milk")
    store.add_face("Alice")

    runtime = PiRuntimeService(config=config, state=state, store=store, logger=logger)
    status = runtime.render_once()

    assert status["snapshot_ready"] is True
    assert status["camera_backend"] == "mock"
    assert status["camera_simulated"] is True
    assert Path(status["snapshot_path"]).exists()
    assert Path(status["metadata_path"]).exists()


def test_runtime_endpoints_return_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUEVISION_CAMERA_BACKEND", "mock")
    monkeypatch.setenv("TRUEVISION_DISPLAY_BACKGROUND", "camera")
    monkeypatch.setenv("TRUEVISION_ENABLE_WINDOW", "0")

    with TestClient(create_app()) as client:
        status = client.get("/api/runtime/status")
        assert status.status_code == 200
        assert status.json()["snapshot_ready"] is True

        checkpoints = client.get("/api/runtime/checkpoints")
        assert checkpoints.status_code == 200
        assert checkpoints.json()["checkpoints"]

        snapshot = client.get("/api/runtime/snapshot")
        assert snapshot.status_code == 200
        assert snapshot.headers["content-type"].startswith("image/jpeg")