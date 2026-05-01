from __future__ import annotations

from dataclasses import dataclass
import time

from truevision_pi.faces.recognizer import RecognizedFace


@dataclass(slots=True)
class PresenceEvent:
    kind: str
    face_id: int
    detection: RecognizedFace | None = None


class PresenceTracker:
    def __init__(self, *, grace_period_sec: float) -> None:
        self._grace_period_sec = grace_period_sec
        self._present: dict[int, float] = {}

    def update(self, detections: list[RecognizedFace]) -> list[PresenceEvent]:
        now = time.monotonic()
        events: list[PresenceEvent] = []
        current_ids = {detection.face_id for detection in detections if detection.face_id is not None}

        for detection in detections:
            if detection.face_id is None:
                continue
            if detection.face_id not in self._present:
                events.append(PresenceEvent(kind="present", face_id=detection.face_id, detection=detection))
            self._present[detection.face_id] = now

        for face_id, last_seen in list(self._present.items()):
            if face_id in current_ids:
                continue
            if now - last_seen >= self._grace_period_sec:
                del self._present[face_id]
                events.append(PresenceEvent(kind="absent", face_id=face_id))
        return events

    def clear(self) -> list[PresenceEvent]:
        events = [PresenceEvent(kind="absent", face_id=face_id) for face_id in self._present]
        self._present.clear()
        return events
