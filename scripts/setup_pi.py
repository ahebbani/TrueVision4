from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import platform

from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database


def _venv_uses_system_site_packages(base_dir: Path) -> bool:
    config_path = base_dir / ".venv" / "pyvenv.cfg"
    if not config_path.exists():
        return False
    for line in config_path.read_text(encoding="utf-8").splitlines():
        if line.lower().startswith("include-system-site-packages"):
            return line.split("=", maxsplit=1)[-1].strip().lower() == "true"
    return False


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def main() -> None:
    config = load_config(RuntimeRole.PI)
    initialize_pi_database(config.pi_db_path)
    linux_host = platform.system() == "Linux"
    checks = {
        "venv_uses_system_site_packages": _venv_uses_system_site_packages(config.base_dir),
        "picamera2_importable": _module_available("picamera2"),
        "cv2_importable": _module_available("cv2"),
    }
    warnings: list[str] = []
    if linux_host and not checks["venv_uses_system_site_packages"]:
        warnings.append("The current .venv does not expose system site packages; Picamera2 and apt-installed OpenCV may be invisible.")
    if linux_host and not checks["picamera2_importable"]:
        warnings.append("picamera2 is not importable from the current environment.")
    if linux_host and not checks["cv2_importable"]:
        warnings.append("cv2 is not importable from the current environment.")

    print(
        json.dumps(
            {
                "status": "ok" if not warnings else "needs-attention",
                "role": config.role.value,
                "platform": platform.platform(),
                "pi_db_path": str(config.pi_db_path),
                "log_dir": str(config.log_dir),
                "checks": checks,
                "warnings": warnings,
                "next_steps": [
                    "Install Pi-specific camera, serial, and ML dependencies.",
                    "Enable UART and camera access on the Raspberry Pi.",
                    "If checks show picamera2 or cv2 missing, rerun make setup-pi before trying make run.",
                    "Use make run-display for the live camera-backed HUD once the camera stack is ready.",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
