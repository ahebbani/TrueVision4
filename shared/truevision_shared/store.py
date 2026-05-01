from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(slots=True)
class FaceRecord:
    id: int
    name: str
    created_at: str
    last_seen_at: str | None
    seen_count: int


@dataclass(slots=True)
class NoteRecord:
    id: int
    content: str
    created_at: str
    is_done: bool
    dismissed_at: str | None


@dataclass(slots=True)
class FaceEmbeddingRecord:
    id: int
    face_id: int
    embedding: bytes
    created_at: str
    quality: float


@dataclass(slots=True)
class MeetingRecord:
    id: int
    person_id: int | None
    started_at: str
    ended_at: str | None
    audio_path: str | None
    transcript: str | None
    summary: str | None
    session_key: str | None
    source_language: str | None
    status: str


@dataclass(slots=True)
class JobRecord:
    id: int
    meeting_id: int
    audio_path: str
    status: str
    transcript: str | None
    summary: str | None
    error: str | None
    created_at: str
    updated_at: str


class PiStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def add_face(self, name: str, *, embedding: bytes | None = None, quality: float = 0.0) -> FaceRecord:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Face name cannot be empty")

        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO faces (name) VALUES (?)",
                (normalized_name,),
            )
            row = connection.execute(
                "SELECT id, name, created_at, last_seen_at, seen_count FROM faces WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            if embedding is not None:
                connection.execute(
                    "INSERT INTO face_embeddings (face_id, embedding, quality) VALUES (?, ?, ?)",
                    (cursor.lastrowid, embedding, float(quality)),
                )
            connection.commit()

        return FaceRecord(*row)

    def get_face(self, face_id: int) -> FaceRecord | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT id, name, created_at, last_seen_at, seen_count FROM faces WHERE id = ?",
                (face_id,),
            ).fetchone()
        return FaceRecord(*row) if row else None

    def list_faces(self) -> list[FaceRecord]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT id, name, created_at, last_seen_at, seen_count FROM faces ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [FaceRecord(*row) for row in rows]

    def add_face_embedding(self, face_id: int, embedding: bytes, *, quality: float = 0.0) -> FaceEmbeddingRecord:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO face_embeddings (face_id, embedding, quality) VALUES (?, ?, ?)",
                (face_id, embedding, float(quality)),
            )
            row = connection.execute(
                "SELECT id, face_id, embedding, created_at, quality FROM face_embeddings WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            connection.commit()
        return FaceEmbeddingRecord(*row)

    def list_face_embeddings(self, *, face_id: int | None = None) -> list[FaceEmbeddingRecord]:
        query = "SELECT id, face_id, embedding, created_at, quality FROM face_embeddings"
        params: tuple[object, ...] = ()
        if face_id is not None:
            query += " WHERE face_id = ?"
            params = (face_id,)
        query += " ORDER BY created_at DESC"
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [FaceEmbeddingRecord(*row) for row in rows]

    def prune_face_embeddings(self, face_id: int, *, keep: int) -> int:
        embeddings = self.list_face_embeddings(face_id=face_id)
        if len(embeddings) <= keep:
            return 0
        to_delete = sorted(embeddings, key=lambda record: (record.quality, record.created_at))[: len(embeddings) - keep]
        with sqlite3.connect(self.database_path) as connection:
            connection.executemany(
                "DELETE FROM face_embeddings WHERE id = ?",
                [(record.id,) for record in to_delete],
            )
            connection.commit()
        return len(to_delete)

    def delete_face(self, face_id: int) -> bool:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute("DELETE FROM faces WHERE id = ?", (face_id,))
            connection.commit()
        return cursor.rowcount > 0

    def mark_face_seen(self, face_id: int) -> FaceRecord | None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE faces SET last_seen_at = CURRENT_TIMESTAMP, seen_count = seen_count + 1 WHERE id = ?",
                (face_id,),
            )
            row = connection.execute(
                "SELECT id, name, created_at, last_seen_at, seen_count FROM faces WHERE id = ?",
                (face_id,),
            ).fetchone()
            connection.commit()
        return FaceRecord(*row) if row else None

    def get_latest_summary(self, face_id: int) -> str | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT summary FROM meetings WHERE person_id = ? AND summary IS NOT NULL ORDER BY id DESC LIMIT 1",
                (face_id,),
            ).fetchone()
        return str(row[0]) if row and row[0] else None

    def create_meeting(
        self,
        *,
        person_id: int | None,
        audio_path: str | None = None,
        session_key: str | None = None,
        source_language: str | None = None,
    ) -> MeetingRecord:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO meetings (person_id, audio_path, session_key, source_language) VALUES (?, ?, ?, ?)",
                (person_id, audio_path, session_key, source_language),
            )
            row = connection.execute(
                "SELECT id, person_id, started_at, ended_at, audio_path, transcript, summary, session_key, source_language, status FROM meetings WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            connection.commit()
        return self._meeting_from_row(row)

    def update_meeting_transcript(self, meeting_id: int, transcript: str, *, append: bool = False) -> MeetingRecord | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT transcript FROM meetings WHERE id = ?",
                (meeting_id,),
            ).fetchone()
            if row is None:
                return None
            new_transcript = transcript.strip()
            if append and row[0]:
                new_transcript = f"{row[0].strip()} {new_transcript}".strip()
            connection.execute(
                "UPDATE meetings SET transcript = ? WHERE id = ?",
                (new_transcript, meeting_id),
            )
            updated = connection.execute(
                "SELECT id, person_id, started_at, ended_at, audio_path, transcript, summary, session_key, source_language, status FROM meetings WHERE id = ?",
                (meeting_id,),
            ).fetchone()
            connection.commit()
        return self._meeting_from_row(updated)

    def finalize_meeting(
        self,
        meeting_id: int,
        *,
        transcript: str,
        summary: str,
        audio_path: str | None = None,
        source_language: str | None = None,
    ) -> MeetingRecord | None:
        with sqlite3.connect(self.database_path) as connection:
            existing = connection.execute(
                "SELECT id FROM meetings WHERE id = ?",
                (meeting_id,),
            ).fetchone()
            if existing is None:
                return None
            connection.execute(
                "UPDATE meetings SET ended_at = CURRENT_TIMESTAMP, transcript = ?, summary = ?, audio_path = COALESCE(?, audio_path), source_language = COALESCE(?, source_language), status = 'done' WHERE id = ?",
                (transcript, summary, audio_path, source_language, meeting_id),
            )
            row = connection.execute(
                "SELECT id, person_id, started_at, ended_at, audio_path, transcript, summary, session_key, source_language, status FROM meetings WHERE id = ?",
                (meeting_id,),
            ).fetchone()
            connection.commit()
        return self._meeting_from_row(row)

    def get_meeting(self, meeting_id: int) -> MeetingRecord | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT id, person_id, started_at, ended_at, audio_path, transcript, summary, session_key, source_language, status FROM meetings WHERE id = ?",
                (meeting_id,),
            ).fetchone()
        return self._meeting_from_row(row) if row else None

    def list_meetings(self, *, limit: int | None = None) -> list[MeetingRecord]:
        query = (
            "SELECT id, person_id, started_at, ended_at, audio_path, transcript, summary, session_key, source_language, status FROM meetings ORDER BY id DESC"
        )
        params: tuple[object, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._meeting_from_row(row) for row in rows]

    def list_meetings_missing_transcript(self) -> list[MeetingRecord]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT id, person_id, started_at, ended_at, audio_path, transcript, summary, session_key, source_language, status FROM meetings WHERE audio_path IS NOT NULL AND (transcript IS NULL OR transcript = '') ORDER BY id ASC"
            ).fetchall()
        return [self._meeting_from_row(row) for row in rows]

    def list_meetings_missing_summary(self) -> list[MeetingRecord]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT id, person_id, started_at, ended_at, audio_path, transcript, summary, session_key, source_language, status FROM meetings WHERE transcript IS NOT NULL AND transcript != '' AND (summary IS NULL OR summary = '') ORDER BY id ASC"
            ).fetchall()
        return [self._meeting_from_row(row) for row in rows]

    def add_note(self, content: str) -> NoteRecord:
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Note content cannot be empty")

        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO notes (content) VALUES (?)",
                (normalized_content,),
            )
            row = connection.execute(
                "SELECT id, content, created_at, is_done, dismissed_at FROM notes WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            connection.commit()

        return self._note_from_row(row)

    def list_notes(self, *, active_only: bool = False) -> list[NoteRecord]:
        query = "SELECT id, content, created_at, is_done, dismissed_at FROM notes"
        if active_only:
            query += " WHERE is_done = 0"
        query += " ORDER BY created_at DESC"
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(query).fetchall()
        return [self._note_from_row(row) for row in rows]

    def mark_note_done(self, note_id: int) -> NoteRecord | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT id, content, created_at, is_done, dismissed_at FROM notes WHERE id = ?",
                (note_id,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE notes SET is_done = 1, dismissed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (note_id,),
            )
            updated = connection.execute(
                "SELECT id, content, created_at, is_done, dismissed_at FROM notes WHERE id = ?",
                (note_id,),
            ).fetchone()
            connection.commit()
        return self._note_from_row(updated)

    @staticmethod
    def serialize_embedding(vector: np.ndarray) -> bytes:
        array = np.asarray(vector, dtype=np.float32)
        return array.tobytes()

    @staticmethod
    def deserialize_embedding(payload: bytes) -> np.ndarray:
        return np.frombuffer(payload, dtype=np.float32)

    @staticmethod
    def _note_from_row(row: tuple[object, ...]) -> NoteRecord:
        note_id, content, created_at, is_done, dismissed_at = row
        return NoteRecord(
            id=int(note_id),
            content=str(content),
            created_at=str(created_at),
            is_done=bool(is_done),
            dismissed_at=str(dismissed_at) if dismissed_at is not None else None,
        )

    @staticmethod
    def _meeting_from_row(row: tuple[object, ...]) -> MeetingRecord:
        return MeetingRecord(
            id=int(row[0]),
            person_id=int(row[1]) if row[1] is not None else None,
            started_at=str(row[2]),
            ended_at=str(row[3]) if row[3] is not None else None,
            audio_path=str(row[4]) if row[4] is not None else None,
            transcript=str(row[5]) if row[5] is not None else None,
            summary=str(row[6]) if row[6] is not None else None,
            session_key=str(row[7]) if row[7] is not None else None,
            source_language=str(row[8]) if row[8] is not None else None,
            status=str(row[9]),
        )


class ServerStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def create_job(self, *, meeting_id: int, audio_path: str) -> JobRecord:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO jobs (meeting_id, audio_path, status) VALUES (?, ?, 'queued')",
                (meeting_id, audio_path),
            )
            row = connection.execute(
                "SELECT id, meeting_id, audio_path, status, transcript, summary, error, created_at, updated_at FROM jobs WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            connection.commit()
        return self._job_from_row(row)

    def update_job(
        self,
        job_id: int,
        *,
        status: str,
        transcript: str | None = None,
        summary: str | None = None,
        error: str | None = None,
    ) -> JobRecord | None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, transcript = COALESCE(?, transcript), summary = COALESCE(?, summary), error = COALESCE(?, error), updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, transcript, summary, error, job_id),
            )
            row = connection.execute(
                "SELECT id, meeting_id, audio_path, status, transcript, summary, error, created_at, updated_at FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            connection.commit()
        return self._job_from_row(row) if row else None

    def get_job_by_meeting(self, meeting_id: int) -> JobRecord | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT id, meeting_id, audio_path, status, transcript, summary, error, created_at, updated_at FROM jobs WHERE meeting_id = ? ORDER BY id DESC LIMIT 1",
                (meeting_id,),
            ).fetchone()
        return self._job_from_row(row) if row else None

    def list_jobs(self, *, status: str | None = None) -> list[JobRecord]:
        query = "SELECT id, meeting_id, audio_path, status, transcript, summary, error, created_at, updated_at FROM jobs"
        params: tuple[object, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY id ASC"
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._job_from_row(row) for row in rows]

    @staticmethod
    def _job_from_row(row: tuple[object, ...]) -> JobRecord:
        return JobRecord(
            id=int(row[0]),
            meeting_id=int(row[1]),
            audio_path=str(row[2]),
            status=str(row[3]),
            transcript=str(row[4]) if row[4] is not None else None,
            summary=str(row[5]) if row[5] is not None else None,
            error=str(row[6]) if row[6] is not None else None,
            created_at=str(row[7]),
            updated_at=str(row[8]),
        )


def serialize_face(face: FaceRecord) -> dict[str, object]:
    return asdict(face)


def serialize_note(note: NoteRecord) -> dict[str, object]:
    return asdict(note)


def serialize_meeting(meeting: MeetingRecord) -> dict[str, object]:
    return asdict(meeting)


def serialize_job(job: JobRecord) -> dict[str, object]:
    return asdict(job)
