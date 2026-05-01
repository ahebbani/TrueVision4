from __future__ import annotations

from truevision_pi.main import create_app as create_pi_app
from truevision_server.app import create_app as create_server_app
from truevision_shared.config import DisplayBackground, Mode, RuntimeRole, load_config


def test_load_config_honors_force_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TRUEVISION_FORCE_MODE", "both")
    monkeypatch.setenv("TRUEVISION_DISPLAY_BACKGROUND", "camera")

    config = load_config(RuntimeRole.PI, base_dir=tmp_path)

    assert config.force_mode is Mode.BOTH
    assert config.display_background is DisplayBackground.CAMERA
    assert config.pi_db_path.exists() is False
    assert config.data_dir.exists()
    assert config.log_dir.exists()


def test_pi_app_exposes_health_endpoint(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUEVISION_FORCE_MODE", "face")

    app = create_pi_app()
    health_route = next(route for route in app.routes if route.path == "/health")

    response = health_route.endpoint()

    assert response["status"] == "ok"
    assert response["mode"] == "face"
    assert (tmp_path / "data" / "faces.db").exists()


def test_server_app_exposes_health_endpoint(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRUEVISION_SERVER_URL", raising=False)

    app = create_server_app()
    health_route = next(route for route in app.routes if route.path == "/health")

    response = health_route.endpoint()

    assert response["status"] == "ok"
    assert "health" in response["services"]
    assert "summarize" in response["services"]
    assert (tmp_path / "data" / "truevision_server.db").exists()
