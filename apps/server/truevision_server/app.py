from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
import uvicorn
from pydantic import BaseModel, Field

from truevision_server.audio_session import AudioSessionProcessor, BackfillWorker
from truevision_server.discovery.advertiser import DiscoveryAdvertiser
from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_server_database
from truevision_shared.logging_utils import configure_logging
from truevision_shared.protocol import WebsocketMessageType
from truevision_shared.store import ServerStore, serialize_job
from truevision_server.summarization import summarize_one_sentence
from truevision_server.telegram import extract_command_text, send_telegram_message


class SummarizeRequest(BaseModel):
    transcript: str = Field(min_length=1)
    previous_summary: str | None = None
    person_name: str | None = None
    max_chars: int = Field(default=140, ge=40, le=280)


class TelegramRequest(BaseModel):
    command: str = Field(min_length=1)


def create_app() -> FastAPI:
    config = load_config(RuntimeRole.SERVER)
    initialize_server_database(config.server_db_path)
    logger = configure_logging(config.log_dir, logger_name="truevision-server")
    store = ServerStore(config.server_db_path)
    processor = AudioSessionProcessor(config, logger, store)
    worker = BackfillWorker(processor)
    advertiser = DiscoveryAdvertiser(config, logger)
    logger.info("server runtime configured")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        advertiser.start()
        worker.start()
        app.state.processor = processor
        app.state.store = store
        yield
        worker.stop()
        advertiser.stop()

    app = FastAPI(title="TrueVision Server", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "role": config.role.value,
            "server_port": config.server_port,
            "server_url": config.server_url,
            "services": [
                "health",
                "summarize",
                "telegram",
                "telegram_llm",
                "ws_audio",
                "backfill",
            ],
            "whisper_model": config.whisper_model,
            "whisper_device": config.whisper_device,
            "translation_source_languages": list(config.translation_source_languages),
        }

    @app.post("/summarize")
    def summarize(request: SummarizeRequest) -> dict[str, Any]:
        summary = summarize_one_sentence(
            request.transcript,
            previous_summary=request.previous_summary,
            person_name=request.person_name,
            max_chars=request.max_chars,
        )
        logger.info("summary generated", extra={"person_name": request.person_name or ""})
        return {"summary": summary, "max_chars": request.max_chars, "source": "local"}

    @app.post("/telegram")
    def telegram(request: TelegramRequest) -> dict[str, Any]:
        message = extract_command_text(request.command)
        result = send_telegram_message(message)
        logger.info("telegram processed", extra={"dry_run": result.dry_run, "sent": result.sent})
        return {
            "message": result.message,
            "sent": result.sent,
            "dry_run": result.dry_run,
            "response": result.response,
        }

    @app.post("/telegram_llm")
    def telegram_llm(request: TelegramRequest) -> dict[str, Any]:
        message = extract_command_text(request.command)
        result = send_telegram_message(message)
        logger.info("telegram llm fallback processed", extra={"dry_run": result.dry_run, "sent": result.sent})
        return {
            "extracted_message": result.message,
            "sent": result.sent,
            "dry_run": result.dry_run,
            "response": result.response,
            "model": "fallback-cleanup",
        }

    @app.websocket("/ws/audio")
    async def websocket_audio(websocket: WebSocket) -> None:
        await websocket.accept()
        active_session_key: str | None = None
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if "text" in message and message["text"] is not None:
                    payload = json.loads(message["text"])
                    message_type = payload.get("type")
                    if message_type == WebsocketMessageType.SESSION_START.value:
                        session = processor.start_session(payload)
                        active_session_key = session.session_key
                    elif message_type == WebsocketMessageType.SESSION_END.value:
                        result = processor.finalize_session(payload)
                        await websocket.send_json(result)
                        active_session_key = None
                elif "bytes" in message and message["bytes"] is not None and active_session_key is not None:
                    caption = processor.append_audio(active_session_key, message["bytes"])
                    if caption is not None:
                        await websocket.send_json(caption)
        except WebSocketDisconnect:
            return

    @app.post("/api/meetings/{meeting_id}/audio")
    async def upload_audio(meeting_id: int, request: Request) -> dict[str, Any]:
        payload = await request.body()
        if not payload:
            raise HTTPException(status_code=400, detail="Missing audio payload")
        audio_path = config.uploads_dir / f"meeting-{meeting_id}.wav"
        audio_path.write_bytes(payload)
        job = processor.enqueue_backfill(meeting_id=meeting_id, audio_path=str(audio_path))
        return {"job": serialize_job(job)}

    @app.get("/api/meetings/{meeting_id}/status")
    def meeting_status(meeting_id: int) -> dict[str, Any]:
        job = store.get_job_by_meeting(meeting_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Meeting not found")
        return {"job": serialize_job(job)}

    @app.post("/api/backfill/trigger")
    def trigger_backfill() -> dict[str, Any]:
        jobs = processor.process_queued_jobs()
        return {"processed": [serialize_job(job) for job in jobs]}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TrueVision server runtime")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--dump-config", action="store_true")
    args = parser.parse_args()

    config = load_config(RuntimeRole.SERVER)
    if args.dump_config:
        print(
            json.dumps(
                {
                    "role": config.role.value,
                    "server_host": config.server_host,
                    "server_port": config.server_port,
                },
                indent=2,
            )
        )
        return

    uvicorn.run(
        create_app(),
        host=args.host or config.server_host,
        port=args.port or config.server_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
