from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path


class RuntimeRole(str, Enum):
    PI = "pi"
    SERVER = "server"


class Mode(str, Enum):
    AUTO = "auto"
    FACE = "face"
    AUDIO = "audio"
    BOTH = "both"


class DisplayBackground(str, Enum):
    BLACK = "black"
    CAMERA = "camera"


class CameraBackend(str, Enum):
    AUTO = "auto"
    MOCK = "mock"
    OPENCV = "opencv"
    PICAMERA2 = "picamera2"


class AudioBackend(str, Enum):
    AUTO = "auto"
    MOCK = "mock"
    SERIAL = "serial"
    FILE = "file"


def _read_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw.strip())


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_mode(name: str, default: Mode) -> Mode:
    raw = _read_env(name, default.value).lower()
    try:
        return Mode(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid mode {raw!r} for {name}") from exc


def _read_background(name: str, default: DisplayBackground) -> DisplayBackground:
    raw = _read_env(name, default.value).lower()
    try:
        return DisplayBackground(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid display background {raw!r} for {name}") from exc


def _read_camera_backend(name: str, default: CameraBackend) -> CameraBackend:
    raw = _read_env(name, default.value).lower()
    try:
        return CameraBackend(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid camera backend {raw!r} for {name}") from exc


def _read_audio_backend(name: str, default: AudioBackend) -> AudioBackend:
    raw = _read_env(name, default.value).lower()
    try:
        return AudioBackend(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid audio backend {raw!r} for {name}") from exc


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw.strip())


def _read_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(slots=True)
class AppConfig:
    role: RuntimeRole
    base_dir: Path
    data_dir: Path
    log_dir: Path
    pi_db_path: Path
    server_db_path: Path
    controller_host: str
    controller_port: int
    server_host: str
    server_port: int
    force_mode: Mode
    display_background: DisplayBackground
    camera_backend: CameraBackend
    audio_backend: AudioBackend
    camera_device_index: int
    frame_width: int
    frame_height: int
    runtime_fps: int
    window_enabled: bool
    serial_port: str
    serial_baud_rate: int
    audio_sample_rate: int
    audio_channels: int
    audio_chunk_samples: int
    caption_interval_sec: float
    caption_window_sec: float
    meeting_absence_grace_sec: float
    server_health_interval_sec: float
    server_connect_timeout_sec: float
    translation_source_languages: tuple[str, ...]
    translation_target_language: str
    translation_detection_min_probability: float
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    launcher_news_url: str
    launcher_weather_url: str
    launcher_instagram_url: str
    launcher_youtube_url: str
    launcher_database_url: str
    audio_dir: Path
    uploads_dir: Path
    runtime_snapshot_dir: Path
    runtime_snapshot_path: Path
    runtime_metadata_path: Path
    server_url: str | None


def load_config(role: RuntimeRole, *, base_dir: Path | None = None) -> AppConfig:
    root_dir = Path(base_dir or Path.cwd()).resolve()
    data_dir = root_dir / "data"
    log_dir = root_dir / "logs"
    audio_dir = data_dir / "audio"
    uploads_dir = data_dir / "uploads"
    runtime_snapshot_dir = data_dir / "runtime"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    runtime_snapshot_dir.mkdir(parents=True, exist_ok=True)

    server_url = os.getenv("TRUEVISION_SERVER_URL")
    return AppConfig(
        role=role,
        base_dir=root_dir,
        data_dir=data_dir,
        log_dir=log_dir,
        pi_db_path=data_dir / "faces.db",
        server_db_path=data_dir / "truevision_server.db",
        controller_host=_read_env("TRUEVISION_CONTROLLER_HOST", "0.0.0.0"),
        controller_port=_read_int("TRUEVISION_CONTROLLER_PORT", 8080),
        server_host=_read_env("TRUEVISION_SERVER_HOST", "0.0.0.0"),
        server_port=_read_int("TRUEVISION_SERVER_PORT", 8008),
        force_mode=_read_mode("TRUEVISION_FORCE_MODE", Mode.AUTO),
        display_background=_read_background(
            "TRUEVISION_DISPLAY_BACKGROUND", DisplayBackground.BLACK
        ),
        camera_backend=_read_camera_backend(
            "TRUEVISION_CAMERA_BACKEND", CameraBackend.AUTO
        ),
        audio_backend=_read_audio_backend("TRUEVISION_AUDIO_BACKEND", AudioBackend.AUTO),
        camera_device_index=_read_int("TRUEVISION_CAMERA_DEVICE", 0),
        frame_width=_read_int("TRUEVISION_FRAME_WIDTH", 960),
        frame_height=_read_int("TRUEVISION_FRAME_HEIGHT", 540),
        runtime_fps=max(1, _read_int("TRUEVISION_RUNTIME_FPS", 2)),
        window_enabled=_read_bool("TRUEVISION_ENABLE_WINDOW", True),
        serial_port=_read_env("TRUEVISION_SERIAL_PORT", "/dev/ttyAMA0"),
        serial_baud_rate=_read_int("TRUEVISION_SERIAL_BAUD_RATE", 921600),
        audio_sample_rate=_read_int("TRUEVISION_AUDIO_SAMPLE_RATE", 16000),
        audio_channels=_read_int("TRUEVISION_AUDIO_CHANNELS", 1),
        audio_chunk_samples=_read_int("TRUEVISION_AUDIO_CHUNK_SAMPLES", 256),
        caption_interval_sec=_read_float("CAPTION_INTERVAL_SEC", 0.7),
        caption_window_sec=_read_float("CAPTION_WINDOW_SEC", 2.0),
        meeting_absence_grace_sec=_read_float("TRUEVISION_ABSENCE_GRACE_SEC", 2.0),
        server_health_interval_sec=_read_float("TRUEVISION_SERVER_HEALTH_INTERVAL_SEC", 5.0),
        server_connect_timeout_sec=_read_float("TRUEVISION_SERVER_CONNECT_TIMEOUT_SEC", 5.0),
        translation_source_languages=_read_csv("TRANSLATION_SOURCE_LANGUAGES", ("es", "de")),
        translation_target_language=_read_env("TRANSLATION_TARGET_LANGUAGE", "en"),
        translation_detection_min_probability=_read_float(
            "TRANSLATION_DETECTION_MIN_PROBABILITY", 0.65
        ),
        whisper_model=_read_env("WHISPER_MODEL", "tiny" if role is RuntimeRole.PI else "small"),
        whisper_device=_read_env("WHISPER_DEVICE", "cpu" if role is RuntimeRole.PI else "auto"),
        whisper_compute_type=_read_env(
            "WHISPER_COMPUTE_TYPE", "int8" if role is RuntimeRole.PI else "float16"
        ),
        launcher_news_url=_read_env("TRUEVISION_NEWS_URL", "https://news.ycombinator.com"),
        launcher_weather_url=_read_env("TRUEVISION_WEATHER_URL", "https://wttr.in/?format=4"),
        launcher_instagram_url=_read_env("TRUEVISION_INSTAGRAM_URL", "https://instagram.com"),
        launcher_youtube_url=_read_env("TRUEVISION_YOUTUBE_URL", "https://youtube.com"),
        launcher_database_url=_read_env("TRUEVISION_DATABASE_URL", "file://{root}/data/truevision-report.html".format(root=root_dir)),
        audio_dir=audio_dir,
        uploads_dir=uploads_dir,
        runtime_snapshot_dir=runtime_snapshot_dir,
        runtime_snapshot_path=runtime_snapshot_dir / "latest-hud.jpg",
        runtime_metadata_path=runtime_snapshot_dir / "latest-hud.json",
        server_url=server_url.strip() if server_url and server_url.strip() else None,
    )
