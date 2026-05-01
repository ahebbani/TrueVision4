from __future__ import annotations

from pathlib import Path
import sys

from truevision_pi.system_imports import import_optional_module


def test_import_optional_module_uses_system_dist_packages(monkeypatch, tmp_path) -> None:
    module_name = "demooptionalbackend"
    package_dir = tmp_path / "dist-packages"
    package_dir.mkdir()
    (package_dir / f"{module_name}.py").write_text("VALUE = 42\n", encoding="utf-8")

    monkeypatch.setattr("truevision_pi.system_imports._should_try_system_site_packages", lambda: True)
    monkeypatch.setattr("truevision_pi.system_imports._candidate_system_site_packages", lambda: [Path(package_dir)])

    sys.modules.pop(module_name, None)
    if str(package_dir) in sys.path:
        sys.path.remove(str(package_dir))

    module = import_optional_module(module_name)

    assert module.VALUE == 42
    assert str(package_dir) in sys.path