from __future__ import annotations

import json
from pathlib import Path

from truevision_pi.audio.transcriber import build_transcriber
from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.logging_utils import configure_logging
from truevision_shared.store import PiStore, serialize_meeting


def main() -> None:
    config = load_config(RuntimeRole.PI)
    initialize_pi_database(config.pi_db_path)
    logger = configure_logging(config.log_dir, logger_name="truevision-backfill-transcripts")
    store = PiStore(config.pi_db_path)
    transcriber = build_transcriber(config, logger)

    updated = []
    for meeting in store.list_meetings_missing_transcript():
        if not meeting.audio_path:
            continue
        result = transcriber.transcribe(Path(meeting.audio_path))
        updated_meeting = store.update_meeting_transcript(meeting.id, result.text)
        if updated_meeting is not None:
            updated.append(serialize_meeting(updated_meeting))
    print(json.dumps({"updated": updated}, indent=2))


if __name__ == "__main__":
    main()
