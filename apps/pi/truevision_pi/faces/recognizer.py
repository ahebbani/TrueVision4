from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import time
from typing import Any

import numpy as np
from PIL import Image

from truevision_shared.config import AppConfig
from truevision_shared.store import PiStore


@dataclass(slots=True)
class RecognizedFace:
    face_id: int | None
    name: str
    bbox: tuple[int, int, int, int]
    confidence: float
    quality: float
    summary: str | None
    seen_count: int
    last_seen_at: str | None
    unknown: bool = False
    recording: bool = False


class FaceRecognizer:
    def __init__(self, config: AppConfig, store: PiStore, logger) -> None:
        self._config = config
        self._store = store
        self._logger = logger
        self._cv2 = self._load_cv2()
        self._cascade = None
        self._last_template_at: dict[int, float] = {}
        if self._cv2 is not None:
            try:  # pragma: no cover - optional runtime path
                cascade_path = self._cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                self._cascade = self._cv2.CascadeClassifier(cascade_path)
            except Exception:
                self._cascade = None

    def recognize(self, image: Image.Image) -> list[RecognizedFace]:
        detections = self._detect_faces(image)
        faces = self._store.list_faces()
        embeddings = self._store.list_face_embeddings()
        embeddings_by_face: dict[int, list[np.ndarray]] = {}
        for template in embeddings:
            embeddings_by_face.setdefault(template.face_id, []).append(self._store.deserialize_embedding(template.embedding))

        if not detections:
            return self._mock_detections(image, faces)

        recognized: list[RecognizedFace] = []
        for bbox in detections:
            embedding = self._embedding_from_box(image, bbox)
            quality = self._quality_for_box(image, bbox)
            match = self._match_face(faces, embeddings_by_face, embedding)
            if match is None:
                recognized.append(
                    RecognizedFace(
                        face_id=None,
                        name="Unknown",
                        bbox=bbox,
                        confidence=0.0,
                        quality=quality,
                        summary=None,
                        seen_count=0,
                        last_seen_at=None,
                        unknown=True,
                    )
                )
                continue

            face, distance = match
            self._maybe_collect_template(face.id, embedding, quality, embeddings_by_face.get(face.id, []))
            recognized.append(
                RecognizedFace(
                    face_id=face.id,
                    name=face.name,
                    bbox=bbox,
                    confidence=max(0.0, 1.0 - distance / 12.0),
                    quality=quality,
                    summary=self._store.get_latest_summary(face.id),
                    seen_count=face.seen_count,
                    last_seen_at=face.last_seen_at,
                )
            )
        return recognized

    def enroll_largest_face(self, name: str, image: Image.Image):
        detections = self._detect_faces(image)
        if detections:
            bbox = max(detections, key=lambda item: item[2] * item[3])
        else:
            bbox = (0, 0, image.width, image.height)
        embedding = self._embedding_from_box(image, bbox)
        quality = self._quality_for_box(image, bbox)
        return self._store.add_face(name, embedding=self._store.serialize_embedding(embedding), quality=quality)

    @staticmethod
    def serialize_detection(detection: RecognizedFace) -> dict[str, Any]:
        return asdict(detection)

    def _load_cv2(self):
        try:  # pragma: no cover - optional runtime path
            import cv2  # type: ignore
        except Exception:
            return None
        return cv2

    def _detect_faces(self, image: Image.Image) -> list[tuple[int, int, int, int]]:
        if self._cv2 is None or self._cascade is None:
            return []
        array = np.array(image.convert("RGB"))
        grayscale = self._cv2.cvtColor(array, self._cv2.COLOR_RGB2GRAY)
        found = self._cascade.detectMultiScale(grayscale, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))
        return [(int(x), int(y), int(w), int(h)) for x, y, w, h in found]

    def _embedding_from_box(self, image: Image.Image, bbox: tuple[int, int, int, int]) -> np.ndarray:
        x, y, w, h = bbox
        region = image.crop((x, y, x + w, y + h)).convert("L").resize((32, 32))
        vector = np.asarray(region, dtype=np.float32).reshape(-1) / 255.0
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm

    def _quality_for_box(self, image: Image.Image, bbox: tuple[int, int, int, int]) -> float:
        x, y, w, h = bbox
        region = np.asarray(image.crop((x, y, x + w, y + h)).convert("L"), dtype=np.float32)
        return float(np.var(region))

    def _match_face(self, faces, embeddings_by_face: dict[int, list[np.ndarray]], probe: np.ndarray):
        best_face = None
        best_distance = math.inf
        for face in faces:
            templates = embeddings_by_face.get(face.id, [])
            for template in templates:
                distance = float(np.linalg.norm(probe - template))
                if distance < best_distance:
                    best_distance = distance
                    best_face = face
        if best_face is None:
            return None
        threshold = 0.9 if len(embeddings_by_face.get(best_face.id, [])) >= 5 else 1.1
        if best_distance > threshold:
            return None
        return best_face, best_distance

    def _maybe_collect_template(self, face_id: int, embedding: np.ndarray, quality: float, existing: list[np.ndarray]) -> None:
        now = time.monotonic()
        last = self._last_template_at.get(face_id, 0.0)
        bootstrap = len(existing) < 5
        cooldown = 0.75 if bootstrap else 5.0
        minimum_quality = 60.0 if bootstrap else 120.0
        if now - last < cooldown or quality < minimum_quality:
            return
        if existing and not bootstrap:
            diversity = min(float(np.linalg.norm(embedding - template)) for template in existing)
            if diversity < 0.2:
                return
        self._store.add_face_embedding(face_id, self._store.serialize_embedding(embedding), quality=quality)
        self._store.prune_face_embeddings(face_id, keep=30)
        self._last_template_at[face_id] = now

    def _mock_detections(self, image: Image.Image, faces) -> list[RecognizedFace]:
        width, height = image.size
        if faces:
            results: list[RecognizedFace] = []
            for index, face in enumerate(faces[:2]):
                left = 80 + index * 180
                top = 100 + index * 30
                results.append(
                    RecognizedFace(
                        face_id=face.id,
                        name=face.name,
                        bbox=(left, top, 120, 120),
                        confidence=0.92,
                        quality=180.0,
                        summary=self._store.get_latest_summary(face.id),
                        seen_count=face.seen_count,
                        last_seen_at=face.last_seen_at,
                    )
                )
            return results
        return [
            RecognizedFace(
                face_id=None,
                name="Unknown",
                bbox=(max(40, width // 2 - 60), max(40, height // 2 - 60), 120, 120),
                confidence=0.0,
                quality=140.0,
                summary=None,
                seen_count=0,
                last_seen_at=None,
                unknown=True,
            )
        ]
