"""Shared contracts and infrastructure for TrueVision."""

from .config import (
    AppConfig,
    AudioBackend,
    CameraBackend,
    DisplayBackground,
    Mode,
    RuntimeRole,
    load_config,
)

__all__ = [
    "AppConfig",
    "AudioBackend",
    "CameraBackend",
    "DisplayBackground",
    "Mode",
    "RuntimeRole",
    "load_config",
]

