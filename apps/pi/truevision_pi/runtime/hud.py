from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import platform
import subprocess
import time
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from truevision_shared.store import NoteRecord


_SYSTEM_METRICS_CACHE = {
    "updated_at": 0.0,
    "cpu_temp_c": None,
    "wifi_signal": "N/A",
}


def render_hud(
    *,
    width: int,
    height: int,
    display_background: str,
    camera_backend: str,
    camera_simulated: bool,
    runtime_status: dict[str, Any],
    notes: list[NoteRecord],
    render_count: int,
    background_image: Image.Image | None,
) -> Image.Image:
    fonts = {
        "time": _load_font(30),
        "body": _load_font(18),
        "small": _load_font(14),
        "caption": _load_font(22),
    }
    frame = Image.new("RGB", (width, height), (0, 0, 0))
    if background_image is not None:
        frame.paste(background_image.resize((width, height)))

    draw = ImageDraw.Draw(frame, "RGBA")
    now = datetime.now()
    _draw_text(draw, (24, 18), now.strftime("%I:%M %p").lstrip("0"), font=fonts["time"], fill=(244, 249, 252))
    _draw_text(draw, (26, 52), now.strftime("%a, %b %d"), font=fonts["body"], fill=(173, 231, 255))

    _draw_status_block(
        draw,
        width=width,
        fonts=fonts,
        mode=runtime_status["active_mode"].upper(),
        requested=runtime_status["requested_mode"].upper(),
        server_connected=bool(runtime_status["server_connected"]),
        camera_backend=f"{camera_backend}{' (sim)' if camera_simulated else ''}",
        session_count=int(runtime_status.get("active_session_count", 0)),
        audio_buffer=float(runtime_status.get("audio_buffer_duration_sec", 0.0)),
    )

    if runtime_status["active_mode"] in {"face", "both"}:
        _draw_faces(draw, runtime_status.get("detected_faces", []), fonts=fonts, width=width, height=height)

    if notes:
        _draw_reminders(draw, notes[:3], fonts=fonts, height=height)

    if runtime_status["active_mode"] in {"audio", "both"}:
        _draw_captions(draw, runtime_status.get("caption_text") or "Listening for speech...", fonts=fonts, width=width, height=height)

    toast_text = runtime_status.get("toast_text")
    if toast_text:
        _draw_center_banner(draw, str(toast_text)[:72], fonts=fonts, width=width, height=height)

    if runtime_status.get("launcher"):
        _draw_center_banner(
            draw,
            f"Launcher active: {runtime_status['launcher']}",
            fonts=fonts,
            width=width,
            height=height,
            y_offset=58,
        )

    return frame


@lru_cache(maxsize=8)
def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _draw_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    shadow_alpha: int = 220,
) -> None:
    x, y = position
    shadow_fill = (0, 0, 0, shadow_alpha)
    draw.text((x + 2, y + 2), text, font=font, fill=shadow_fill)
    draw.text((x, y), text, font=font, fill=fill)


def _draw_status_block(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    fonts: dict[str, ImageFont.ImageFont],
    mode: str,
    requested: str,
    server_connected: bool,
    camera_backend: str,
    session_count: int,
    audio_buffer: float,
) -> None:
    right = width - 24
    cpu_temp_c, wifi_signal = _get_system_metrics()
    lines = [
        f"MODE {mode}",
        f"REQ {requested}",
        f"CAM {camera_backend}",
        f"SESSIONS {session_count}",
        f"AUDIO {audio_buffer:.1f}s",
    ]
    server_label = "SERVER UP" if server_connected else "SERVER DOWN"
    server_color = (102, 234, 141) if server_connected else (255, 117, 117)
    y = 20
    cpu_text = f"CPU {_format_cpu_temp(cpu_temp_c)}"
    _draw_text(draw, (width - 250, y), cpu_text, font=fonts["small"], fill=_cpu_temp_color(cpu_temp_c))
    _draw_right_text(draw, right, y, f"WIFI {wifi_signal}", font=fonts["small"], fill=(194, 226, 241))
    dot_x = right - 154
    draw.ellipse((dot_x, y + 31, dot_x + 10, y + 41), fill=server_color + (255,))
    _draw_right_text(draw, right, y + 24, server_label, font=fonts["body"], fill=(244, 249, 252))
    for index, line in enumerate(lines):
        _draw_right_text(
            draw,
            right,
            y + 52 + index * 18,
            line,
            font=fonts["small"],
            fill=(194, 226, 241),
        )


def _draw_right_text(
    draw: ImageDraw.ImageDraw,
    right: int,
    top: int,
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    _draw_text(draw, (right - width, top), text, font=font, fill=fill)


def _draw_faces(
    draw: ImageDraw.ImageDraw,
    faces: list[dict[str, Any]],
    *,
    fonts: dict[str, ImageFont.ImageFont],
    width: int,
    height: int,
) -> None:
    for face in faces[:4]:
        bbox = face.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        x, y, box_width, box_height = [int(value) for value in bbox]
        if box_width <= 0 or box_height <= 0:
            continue
        left = max(0, min(x, width - 1))
        top = max(0, min(y, height - 1))
        right = max(left + 1, min(x + box_width, width - 1))
        bottom = max(top + 1, min(y + box_height, height - 1))
        highlight = (255, 191, 89, 255) if face.get("unknown") else (104, 245, 196, 255)
        draw.rectangle((left, top, right, bottom), outline=highlight, width=3)

        summary = str(face.get("summary") or "")
        lines = [
            face_label := _face_title(face),
            f"Last {_format_last_seen(face.get('last_seen_at'))}",
        ]
        if summary:
            lines.append(_truncate_text(draw, summary, fonts["small"], 250))
        if face.get("recording"):
            lines.append("REC")

        label_left = max(12, left)
        label_top = max(12, top - (18 * len(lines) + 18))
        label_width = min(284, width - label_left - 12)
        label_height = 12 + len(lines) * 18
        draw.rounded_rectangle(
            (label_left, label_top, label_left + label_width, label_top + label_height),
            radius=12,
            fill=(3, 7, 10, 136),
            outline=(highlight[0], highlight[1], highlight[2], 140),
            width=2,
        )
        for index, line in enumerate(lines):
            fill = (244, 249, 252) if index == 0 else (209, 227, 237)
            if line == "REC":
                fill = (255, 117, 117)
            _draw_text(draw, (label_left + 10, label_top + 8 + index * 18), line, font=fonts["small"], fill=fill)


def _face_title(face: dict[str, Any]) -> str:
    seen_count = int(face.get("seen_count") or 0)
    return f"{face.get('name', 'Unknown')} ({seen_count}x)"


def _draw_reminders(
    draw: ImageDraw.ImageDraw,
    notes: list[NoteRecord],
    *,
    fonts: dict[str, ImageFont.ImageFont],
    height: int,
) -> None:
    base_y = height - 92
    _draw_text(draw, (24, base_y - 28), "REMINDERS", font=fonts["small"], fill=(173, 231, 255))
    for index, note in enumerate(notes[:3]):
        _draw_text(
            draw,
            (24, base_y + index * 20),
            _truncate_text(draw, f"- {note.content}", fonts["body"], 320),
            font=fonts["body"],
            fill=(244, 249, 252),
        )


def _draw_captions(
    draw: ImageDraw.ImageDraw,
    caption_text: str,
    *,
    fonts: dict[str, ImageFont.ImageFont],
    width: int,
    height: int,
) -> None:
    max_width = width - 180
    lines = _wrap_text(draw, caption_text, fonts["caption"], max_width=max_width, max_lines=2)
    strip_height = 56 + max(0, len(lines) - 1) * 24
    strip_top = height - strip_height - 22
    draw.rounded_rectangle(
        (90, strip_top, width - 90, height - 18),
        radius=18,
        fill=(3, 7, 10, 166),
        outline=(123, 220, 255, 84),
        width=2,
    )
    _draw_text(draw, (112, strip_top + 14), "CAPTIONS", font=fonts["small"], fill=(173, 231, 255))
    for index, line in enumerate(lines):
        _draw_text(draw, (112, strip_top + 32 + index * 24), line, font=fonts["caption"], fill=(244, 249, 252))


def _draw_center_banner(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    fonts: dict[str, ImageFont.ImageFont],
    width: int,
    height: int,
    y_offset: int = 0,
) -> None:
    box = draw.textbbox((0, 0), text, font=fonts["body"])
    banner_width = min(width - 120, (box[2] - box[0]) + 40)
    left = (width - banner_width) // 2
    top = height // 2 - 24 + y_offset
    draw.rounded_rectangle(
        (left, top, left + banner_width, top + 48),
        radius=18,
        fill=(3, 7, 10, 182),
        outline=(123, 220, 255, 84),
        width=2,
    )
    _draw_text(draw, (left + 20, top + 14), text, font=fonts["body"], fill=(244, 249, 252))


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    *,
    max_width: int,
    max_lines: int,
) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(words) > len(" ".join(lines).split()):
        lines[-1] = _truncate_text(draw, f"{lines[-1]}...", font, max_width)
    return lines[:max_lines]


def _truncate_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    trimmed = text
    while trimmed and draw.textlength(f"{trimmed}...", font=font) > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed}..." if trimmed else "..."


def _get_system_metrics() -> tuple[float | None, str]:
    now = time.monotonic()
    if now - float(_SYSTEM_METRICS_CACHE["updated_at"]) >= 2.0:
        _SYSTEM_METRICS_CACHE["updated_at"] = now
        _SYSTEM_METRICS_CACHE["cpu_temp_c"] = _read_cpu_temp_c()
        _SYSTEM_METRICS_CACHE["wifi_signal"] = _read_wifi_signal()
    return _SYSTEM_METRICS_CACHE["cpu_temp_c"], str(_SYSTEM_METRICS_CACHE["wifi_signal"])


def _read_cpu_temp_c() -> float | None:
    thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return float(thermal_path.read_text(encoding="utf-8").strip()) / 1000.0
    except Exception:
        return None


def _read_wifi_signal() -> str:
    if platform.system() != "Linux":
        return "N/A"
    try:
        result = subprocess.run(
            ["iwconfig", "wlan0"],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.25,
        )
    except Exception:
        return "N/A"
    output = result.stdout
    marker = "Signal level="
    if marker not in output:
        return "N/A"
    start = output.index(marker) + len(marker)
    signal = output[start:].split()[0]
    return signal.replace("dBm", " dBm") if "dBm" in signal else signal


def _format_cpu_temp(value: float | None) -> str:
    return f"{value:.1f}C" if value is not None else "N/A"


def _cpu_temp_color(value: float | None) -> tuple[int, int, int]:
    if value is None:
        return (194, 226, 241)
    if value > 75:
        return (255, 117, 117)
    if value > 60:
        return (255, 208, 115)
    return (102, 234, 141)


def _format_last_seen(value: Any) -> str:
    if not value:
        return "now"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"
