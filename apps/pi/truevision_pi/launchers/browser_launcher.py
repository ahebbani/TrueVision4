from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from scripts.visualize_db import render_report
from truevision_shared.config import AppConfig


class BrowserLauncher:
    def __init__(self, config: AppConfig, logger) -> None:
        self._config = config
        self._logger = logger
        self._process: subprocess.Popen[str] | None = None
        self._current_target: str | None = None

    def open(self, target: str) -> dict[str, object]:
        url = self._resolve_target(target)
        self.close()
        command = self._build_command(url)
        dry_run = command is None or bool(os.getenv("PYTEST_CURRENT_TEST"))
        if dry_run:
            self._current_target = target
            self._logger.info("launcher dry run", extra={"target": target, "url": url})
            return {"target": target, "url": url, "dry_run": True}

        self._process = subprocess.Popen(command)
        self._current_target = target
        self._logger.info("launcher started", extra={"target": target, "command": command})
        return {"target": target, "url": url, "dry_run": False}

    def close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
        self._current_target = None

    def _resolve_target(self, target: str) -> str:
        match target:
            case "news":
                return self._config.launcher_news_url
            case "weather":
                return self._config.launcher_weather_url
            case "instagram":
                return self._config.launcher_instagram_url
            case "youtube":
                return self._config.launcher_youtube_url
            case "database":
                output = render_report(self._config.data_dir / "truevision-report.html")
                return output.as_uri()
            case _:
                return target

    def _build_command(self, url: str) -> list[str] | None:
        chromium = shutil.which("chromium-browser") or shutil.which("chromium") or shutil.which("google-chrome")
        if chromium and sys.platform.startswith("linux"):
            return [chromium, "--kiosk", url]
        opener = shutil.which("open")
        if opener and sys.platform == "darwin":
            return [opener, url]
        return None
