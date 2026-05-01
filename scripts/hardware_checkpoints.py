from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib import error, request

from truevision_shared.config import RuntimeRole, load_config


def fetch_json(url: str) -> dict[str, object] | None:
    try:
        with request.urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, error.URLError, json.JSONDecodeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Check production checkpoints for the current TrueVision Pi slice")
    parser.add_argument("--controller-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()

    config = load_config(RuntimeRole.PI)
    health = fetch_json(f"{args.controller_url}/health")
    runtime = fetch_json(f"{args.controller_url}/api/runtime/status")
    checkpoint_payload = fetch_json(f"{args.controller_url}/api/runtime/checkpoints")
    meeting_payload = fetch_json(f"{args.controller_url}/api/meetings")
    meetings_raw = meeting_payload.get("meetings") if isinstance(meeting_payload, dict) else None
    meetings = meetings_raw if isinstance(meetings_raw, list) else []

    report = {
        "slice": "pi-runtime-audio-face-server",
        "implemented": [
            "Pi controller HTTP server",
            "Background HUD snapshot renderer",
            "Black-background HUD mode",
            "Camera-background run-display mode with backend fallback",
            "Snapshot and checkpoint APIs",
            "Mock or serial audio ingestion",
            "Meeting persistence and live caption pipeline",
            "Server websocket offload client",
            "Mock or OpenCV face recognition",
        ],
        "artifacts": {
            "pi_db_path": str(config.pi_db_path),
            "snapshot_path": str(config.runtime_snapshot_path),
            "metadata_path": str(config.runtime_metadata_path),
        },
        "controller_reachable": health is not None,
        "runtime_reachable": runtime is not None,
        "controller_health": health,
        "runtime_status": runtime,
        "runtime_checkpoints": checkpoint_payload["checkpoints"] if checkpoint_payload else [],
        "meetings_count": len(meetings),
        "local_files": {
            "db_exists": Path(config.pi_db_path).exists(),
            "snapshot_exists": Path(config.runtime_snapshot_path).exists(),
            "metadata_exists": Path(config.runtime_metadata_path).exists(),
        },
        "next_hardware_checks": [
            "Run make run on the Pi and verify a fullscreen HUD appears or snapshot files update if GUI is unavailable.",
            "Run make run-display on the Pi and confirm camera_backend is not simulated in /api/runtime/status.",
            "Switch to AUDIO mode, wait at least 1 second, switch back to FACE, then confirm a completed meeting appears in /api/meetings.",
            "Switch to BOTH mode with the server live and confirm caption_text changes while /api/runtime/status shows server_connected=true.",
            "Run make checkpoints while the Pi app is live and confirm camera_background, audio_pipeline, face_pipeline, and display_window are pass on production hardware.",
        ],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
