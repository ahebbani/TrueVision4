from __future__ import annotations

from html import escape
from pathlib import Path

from truevision_shared.config import RuntimeRole, load_config
from truevision_shared.db import initialize_pi_database
from truevision_shared.store import PiStore


def render_report(output_path: Path) -> Path:
    config = load_config(RuntimeRole.PI)
    initialize_pi_database(config.pi_db_path)
    store = PiStore(config.pi_db_path)
    faces = store.list_faces()
    notes = store.list_notes(active_only=False)
    meetings = store.list_meetings(limit=50)
    embeddings = store.list_face_embeddings()

    rows = "".join(
        f"<tr><td>{face.id}</td><td>{escape(face.name)}</td><td>{face.seen_count}</td><td>{escape(face.created_at)}</td></tr>"
        for face in faces
    ) or "<tr><td colspan='4'>No faces enrolled yet.</td></tr>"
    note_rows = "".join(
        f"<tr><td>{note.id}</td><td>{escape(note.content)}</td><td>{'done' if note.is_done else 'active'}</td><td>{escape(note.created_at)}</td></tr>"
        for note in notes
    ) or "<tr><td colspan='4'>No notes saved yet.</td></tr>"
    meeting_rows = "".join(
      f"<tr><td>{meeting.id}</td><td>{meeting.person_id or '-'}</td><td>{escape(meeting.status)}</td><td>{escape(meeting.summary or '')}</td><td>{escape(meeting.started_at)}</td></tr>"
      for meeting in meetings
    ) or "<tr><td colspan='5'>No meetings saved yet.</td></tr>"
    embedding_rows = "".join(
      f"<tr><td>{record.id}</td><td>{record.face_id}</td><td>{record.quality:.1f}</td><td>{escape(record.created_at)}</td></tr>"
      for record in embeddings
    ) or "<tr><td colspan='4'>No embeddings saved yet.</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <title>TrueVision Report</title>
  <style>
    body {{ font-family: "Avenir Next", sans-serif; margin: 32px; background: #0f1720; color: #f8fafc; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 28px; }}
    td, th {{ border: 1px solid #334155; padding: 10px; text-align: left; }}
    th {{ background: #16212d; }}
    h1, h2 {{ margin-top: 0; }}
  </style>
</head>
<body>
  <h1>TrueVision Database Report</h1>
  <h2>Faces</h2>
  <table>
    <thead><tr><th>ID</th><th>Name</th><th>Seen Count</th><th>Created</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <h2>Notes</h2>
  <table>
    <thead><tr><th>ID</th><th>Content</th><th>Status</th><th>Created</th></tr></thead>
    <tbody>{note_rows}</tbody>
  </table>
  <h2>Meetings</h2>
  <table>
    <thead><tr><th>ID</th><th>Person ID</th><th>Status</th><th>Summary</th><th>Started</th></tr></thead>
    <tbody>{meeting_rows}</tbody>
  </table>
  <h2>Embeddings</h2>
  <table>
    <thead><tr><th>ID</th><th>Face ID</th><th>Quality</th><th>Created</th></tr></thead>
    <tbody>{embedding_rows}</tbody>
  </table>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    config = load_config(RuntimeRole.PI)
    output_path = render_report(config.data_dir / "truevision-report.html")
    print(output_path)


if __name__ == "__main__":
    main()
