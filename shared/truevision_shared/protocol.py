from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json


FRAME_PREFIX = b"\xAA\x55"


class PacketType(int, Enum):
    AUDIO_DATA = 0x01
    MODE_CHANGE = 0x02
    MARKER = 0x03


class WebsocketMessageType(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    CAPTION = "caption"
    RESULT = "result"


LANGUAGE_LABELS = {
    "es": "Spanish",
    "de": "German",
    "en": "English",
    "fr": "French",
    "it": "Italian",
}


@dataclass(slots=True)
class SerialFrame:
    packet_type: PacketType
    data: bytes


@dataclass(slots=True)
class CaptionMessage:
    type: str
    text: str
    session_key: str
    source_language: str | None = None


@dataclass(slots=True)
class ResultMessage:
    type: str
    session_key: str
    meeting_id: int | None
    transcript: str
    summary: str


def compute_checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def build_frame(packet_type: PacketType, data: bytes) -> bytes:
    length = len(data)
    return (
        FRAME_PREFIX
        + bytes([int(packet_type), length & 0xFF, (length >> 8) & 0xFF])
        + data
        + bytes([compute_checksum(data)])
    )


class SerialFrameParser:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, payload: bytes) -> list[SerialFrame]:
        self._buffer.extend(payload)
        frames: list[SerialFrame] = []

        while True:
            if len(self._buffer) < 6:
                return frames
            prefix_index = self._buffer.find(FRAME_PREFIX)
            if prefix_index == -1:
                self._buffer.clear()
                return frames
            if prefix_index > 0:
                del self._buffer[:prefix_index]
            if len(self._buffer) < 6:
                return frames

            packet_type_raw = self._buffer[2]
            payload_length = self._buffer[3] | (self._buffer[4] << 8)
            frame_length = 2 + 1 + 2 + payload_length + 1
            if len(self._buffer) < frame_length:
                return frames

            payload_bytes = bytes(self._buffer[5 : 5 + payload_length])
            checksum = self._buffer[5 + payload_length]
            if compute_checksum(payload_bytes) != checksum:
                del self._buffer[:2]
                continue

            try:
                packet_type = PacketType(packet_type_raw)
            except ValueError:
                del self._buffer[:frame_length]
                continue

            frames.append(SerialFrame(packet_type=packet_type, data=payload_bytes))
            del self._buffer[:frame_length]


def format_caption(text: str, source_language: str | None = None) -> str:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return ""
    if not source_language or source_language.lower() == "en":
        return cleaned
    label = LANGUAGE_LABELS.get(source_language.lower(), source_language.upper())
    return f"({label}) {cleaned}"


def caption_message(text: str, session_key: str, source_language: str | None = None) -> dict[str, object]:
    return asdict(
        CaptionMessage(
            type=WebsocketMessageType.CAPTION.value,
            text=format_caption(text, source_language),
            session_key=session_key,
            source_language=source_language,
        )
    )


def result_message(
    *, session_key: str, meeting_id: int | None, transcript: str, summary: str
) -> dict[str, object]:
    return asdict(
        ResultMessage(
            type=WebsocketMessageType.RESULT.value,
            session_key=session_key,
            meeting_id=meeting_id,
            transcript=transcript,
            summary=summary,
        )
    )


def control_message(message_type: WebsocketMessageType, **payload: object) -> dict[str, object]:
    return {"type": message_type.value, **payload}


def encode_json_message(message: dict[str, object]) -> str:
    return json.dumps(message, separators=(",", ":"), ensure_ascii=True)
