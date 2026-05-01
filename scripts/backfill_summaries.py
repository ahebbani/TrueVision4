from __future__ import annotations

import json

from truevision_pi.audio.server_connection import ServerConnection
from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.logging_utils import configure_logging
from truevision_shared.store import PiStore, serialize_meeting
from truevision_server.summarization import summarize_one_sentence


def main() -> None:
    config = load_config(RuntimeRole.PI)
    initialize_pi_database(config.pi_db_path)
    logger = configure_logging(config.log_dir, logger_name="truevision-backfill-summaries")
    store = PiStore(config.pi_db_path)
    server_connection = ServerConnection(config, logger)

    updated = []
    for meeting in store.list_meetings_missing_summary():
        person_name = store.get_face(meeting.person_id).name if meeting.person_id else None
        summary = server_connection.summarize(
            transcript=meeting.transcript or "",
            previous_summary=store.get_latest_summary(meeting.person_id) if meeting.person_id else None,
            person_name=person_name,
            max_chars=140,
        ) or summarize_one_sentence(meeting.transcript or "", person_name=person_name, max_chars=140)
        updated_meeting = store.finalize_meeting(
            meeting.id,
            transcript=meeting.transcript or "",
            summary=summary,
            audio_path=meeting.audio_path,
            source_language=meeting.source_language,
        )
        if updated_meeting is not None:
            updated.append(serialize_meeting(updated_meeting))
    print(json.dumps({"updated": updated}, indent=2))


if __name__ == "__main__":
    main()
