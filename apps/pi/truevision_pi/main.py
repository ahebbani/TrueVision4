from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
import uvicorn
from pydantic import BaseModel, Field

from truevision_pi.runtime.service import PiRuntimeService
from truevision_shared.config import Mode, RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.logging_utils import configure_logging
from truevision_shared.pi_state import PiRuntimeState, serialize_status
from truevision_shared.store import PiStore, serialize_face, serialize_meeting, serialize_note


INDEX_HTML = (Path(__file__).resolve().parent / "static" / "index.html").read_text(encoding="utf-8")


class ModeRequest(BaseModel):
    mode: Mode


class NoteCreateRequest(BaseModel):
    content: str = Field(min_length=1)


class FaceCreateRequest(BaseModel):
    name: str = Field(min_length=1)


class LauncherRequest(BaseModel):
    target: str = Field(min_length=1)


def create_app() -> FastAPI:
    config = load_config(RuntimeRole.PI)
    initialize_pi_database(config.pi_db_path)
    logger = configure_logging(config.log_dir, logger_name="truevision-pi")
    state = PiRuntimeState(config)
    store = PiStore(config.pi_db_path)
    runtime_service = PiRuntimeService(config=config, state=state, store=store, logger=logger)
    logger.info(
        "pi runtime configured",
        extra={
            "mode": config.force_mode.value,
            "display_background": config.display_background.value,
        },
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime_service.start()
        app.state.runtime_service = runtime_service
        yield
        runtime_service.stop()

    app = FastAPI(title="TrueVision Pi", version="0.1.0", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_HTML

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "role": config.role.value,
            "mode": config.force_mode.value,
            "display_background": config.display_background.value,
            "controller_port": config.controller_port,
            "server_url": config.server_url,
            "server_connected": state.snapshot().server_connected,
        }

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        snapshot = serialize_status(state.snapshot())
        snapshot.update(
            {
                "log_dir": str(config.log_dir),
                "db_path": str(config.pi_db_path),
                "runtime": runtime_service.status(),
            }
        )
        return snapshot

    @app.get("/api/runtime/status")
    def runtime_status() -> dict[str, Any]:
        return runtime_service.status()

    @app.get("/api/runtime/checkpoints")
    def runtime_checkpoints() -> dict[str, Any]:
        return {"checkpoints": runtime_service.checkpoints()}

    @app.get("/api/runtime/snapshot")
    def runtime_snapshot() -> FileResponse:
        if not config.runtime_snapshot_path.exists():
            raise HTTPException(status_code=404, detail="Runtime snapshot not ready")
        return FileResponse(config.runtime_snapshot_path, media_type="image/jpeg")

    @app.post("/api/mode")
    def set_mode(request: ModeRequest) -> dict[str, Any]:
        snapshot = state.set_requested_mode(request.mode)
        logger.info("mode updated", extra={"requested_mode": request.mode.value})
        return serialize_status(snapshot)

    @app.get("/api/notes")
    def list_notes() -> dict[str, Any]:
        return {"notes": [serialize_note(note) for note in store.list_notes(active_only=False)]}

    @app.post("/api/notes")
    def create_note(request: NoteCreateRequest) -> dict[str, Any]:
        note = store.add_note(request.content)
        logger.info("note created", extra={"note_id": note.id})
        return {"note": serialize_note(note)}

    @app.post("/api/notes/{note_id}/done")
    def complete_note(note_id: int) -> dict[str, Any]:
        note = store.mark_note_done(note_id)
        if note is None:
            raise HTTPException(status_code=404, detail="Note not found")
        logger.info("note completed", extra={"note_id": note.id})
        return {"note": serialize_note(note)}

    @app.get("/api/faces")
    def list_faces() -> dict[str, Any]:
        return {"faces": [serialize_face(face) for face in store.list_faces()]}

    @app.post("/api/faces")
    def create_face(request: FaceCreateRequest) -> dict[str, Any]:
        face = runtime_service.enroll_face(request.name)
        logger.info("face enrolled", extra={"face_id": face.id})
        return {"face": serialize_face(face)}

    @app.post("/api/launchers/open")
    def open_launcher(request: LauncherRequest) -> dict[str, Any]:
        snapshot = runtime_service.open_launcher(request.target)
        logger.info("launcher opened", extra={"target": request.target})
        return snapshot

    @app.post("/api/launchers/close")
    def close_launcher() -> dict[str, Any]:
        snapshot = runtime_service.close_launcher()
        logger.info("launcher closed")
        return snapshot

    @app.get("/api/meetings")
    def list_meetings() -> dict[str, Any]:
        return {"meetings": [serialize_meeting(meeting) for meeting in store.list_meetings(limit=20)]}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TrueVision Pi runtime")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--dump-config", action="store_true")
    args = parser.parse_args()

    config = load_config(RuntimeRole.PI)
    if args.dump_config:
        print(
            json.dumps(
                {
                    "role": config.role.value,
                    "controller_host": config.controller_host,
                    "controller_port": config.controller_port,
                    "mode": config.force_mode.value,
                    "display_background": config.display_background.value,
                    "camera_backend": config.camera_backend.value,
                    "frame_width": config.frame_width,
                    "frame_height": config.frame_height,
                    "runtime_fps": config.runtime_fps,
                    "window_enabled": config.window_enabled,
                },
                indent=2,
            )
        )
        return

    uvicorn.run(
        create_app(),
        host=args.host or config.controller_host,
        port=args.port or config.controller_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
