from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
import math
from typing import Protocol

from PIL import Image, ImageDraw

from truevision_shared.config import AppConfig, CameraBackend


@dataclass(slots=True)
class CameraFrame:
    image: Image.Image
    backend: str
    simulated: bool


class FrameSource(Protocol):
    backend_name: str
    simulated: bool

    def start(self) -> None: ...

    def capture(self) -> CameraFrame: ...

    def stop(self) -> None: ...


class MockFrameSource:
    backend_name = CameraBackend.MOCK.value
    simulated = True

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._frame_index = 0

    def start(self) -> None:
        return None

    def capture(self) -> CameraFrame:
        width = self._config.frame_width
        height = self._config.frame_height
        image = Image.new("RGB", (width, height), (8, 18, 28))
        draw = ImageDraw.Draw(image)

        for step in range(0, width, max(1, width // 12)):
            draw.line((step, 0, step, height), fill=(18, 34, 48), width=1)
        for step in range(0, height, max(1, height // 8)):
            draw.line((0, step, width, step), fill=(18, 34, 48), width=1)

        orb_x = int((math.sin(self._frame_index / 4) + 1) * 0.5 * (width - 120)) + 60
        orb_y = int((math.cos(self._frame_index / 5) + 1) * 0.5 * (height - 120)) + 60
        draw.ellipse((orb_x - 42, orb_y - 42, orb_x + 42, orb_y + 42), fill=(38, 112, 161))
        draw.text((24, height - 42), "SIMULATED CAMERA", fill=(180, 220, 255))

        self._frame_index += 1
        return CameraFrame(image=image, backend=self.backend_name, simulated=self.simulated)

    def stop(self) -> None:
        return None


class OpenCVFrameSource:
    backend_name = CameraBackend.OPENCV.value
    simulated = False

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._cv2 = None
        self._capture = None

    def start(self) -> None:
        if self._capture is not None:
            return
        import cv2  # type: ignore

        self._cv2 = cv2
        capture = cv2.VideoCapture(self._config.camera_device_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.frame_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.frame_height)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError("OpenCV camera source could not be opened")
        self._capture = capture

    def capture(self) -> CameraFrame:
        if self._capture is None:
            self.start()
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise RuntimeError("OpenCV camera capture failed")

        image = Image.fromarray(frame[:, :, ::-1]).resize(
            (self._config.frame_width, self._config.frame_height)
        )
        return CameraFrame(image=image, backend=self.backend_name, simulated=self.simulated)

    def stop(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class Picamera2FrameSource:
    backend_name = CameraBackend.PICAMERA2.value
    simulated = False

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._camera = None

    def start(self) -> None:
        if self._camera is not None:
            return
        from picamera2 import Picamera2  # type: ignore

        camera = Picamera2()
        configuration = camera.create_preview_configuration(
            main={
                "format": "RGB888",
                "size": (self._config.frame_width, self._config.frame_height),
            }
        )
        camera.configure(configuration)
        camera.start()
        self._camera = camera

    def capture(self) -> CameraFrame:
        if self._camera is None:
            self.start()
        frame = self._camera.capture_array("main")
        image = Image.fromarray(frame).resize(
            (self._config.frame_width, self._config.frame_height)
        )
        return CameraFrame(image=image, backend=self.backend_name, simulated=self.simulated)

    def stop(self) -> None:
        if self._camera is not None:
            self._camera.stop()
            self._camera.close()
            self._camera = None


def build_frame_source(config: AppConfig, logger: Logger) -> FrameSource:
    if config.camera_backend is CameraBackend.MOCK:
        logger.info("camera backend forced to mock")
        return MockFrameSource(config)

    candidates: list[tuple[str, type[object]]] = []
    if config.camera_backend is CameraBackend.PICAMERA2:
        candidates = [(CameraBackend.PICAMERA2.value, Picamera2FrameSource)]
    elif config.camera_backend is CameraBackend.OPENCV:
        candidates = [(CameraBackend.OPENCV.value, OpenCVFrameSource)]
    else:
        candidates = [
            (CameraBackend.PICAMERA2.value, Picamera2FrameSource),
            (CameraBackend.OPENCV.value, OpenCVFrameSource),
        ]

    for name, source_class in candidates:
        try:
            source = source_class(config)  # type: ignore[call-arg]
            source.start()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - exercised only with optional deps
            logger.warning("camera backend unavailable", extra={"backend": name, "error": str(exc)})
            continue
        logger.info("camera backend selected", extra={"backend": name})
        return source  # type: ignore[return-value]

    logger.warning("falling back to simulated camera backend")
    return MockFrameSource(config)
