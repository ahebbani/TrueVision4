from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys


def import_optional_module(module_name: str):
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name or not _should_try_system_site_packages():
            raise
        if _add_system_site_packages():
            return import_module(module_name)
        raise ModuleNotFoundError(_missing_dependency_message(module_name)) from exc


def _should_try_system_site_packages() -> bool:
    return sys.platform.startswith("linux") and sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _add_system_site_packages() -> bool:
    added = False
    for candidate in _candidate_system_site_packages():
        candidate_text = str(candidate)
        if not candidate.is_dir() or candidate_text in sys.path:
            continue
        sys.path.append(candidate_text)
        added = True
    return added


def _candidate_system_site_packages() -> list[Path]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return [
        Path("/usr/lib/python3/dist-packages"),
        Path("/usr/local/lib/python3/dist-packages"),
        Path(f"/usr/lib/python{version}/dist-packages"),
        Path(f"/usr/local/lib/python{version}/dist-packages"),
    ]


def _missing_dependency_message(module_name: str) -> str:
    return (
        f"{module_name} is unavailable in the current venv. "
        "On Raspberry Pi OS these packages are usually installed with apt; "
        "rerun make setup-pi or recreate .venv with --system-site-packages."
    )