from __future__ import annotations

import json

from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.store import PiStore, serialize_meeting
from truevision_server.summarization import summarize_one_sentence


def main() -> None:
    config = load_config(RuntimeRole.PI)
    initialize_pi_database(config.pi_db_path)
    store = PiStore(config.pi_db_path)

    updated = []
    for meeting in store.list_meetings_missing_summary():
        person_name = store.get_face(meeting.person_id).name if meeting.person_id else None
        summary = summarize_one_sentence(meeting.transcript or "", person_name=person_name, max_chars=140)
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
