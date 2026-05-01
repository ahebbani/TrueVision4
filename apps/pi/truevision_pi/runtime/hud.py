from __future__ import annotations

from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from truevision_shared.store import NoteRecord


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
    font = ImageFont.load_default()
    frame = Image.new("RGB", (width, height), (0, 0, 0))
    if background_image is not None:
        frame.paste(background_image.resize((width, height)))
        frame = _dim_background(frame, alpha=108)

    draw = ImageDraw.Draw(frame, "RGBA")
    now = datetime.now()
    _panel(draw, 18, 18, 210, 72)
    draw.text((30, 28), now.strftime("%I:%M %p").lstrip("0"), fill=(255, 255, 255), font=font)
    draw.text((30, 52), now.strftime("%a, %b %d"), fill=(192, 215, 235), font=font)

    _panel(draw, width - 278, 18, 260, 96)
    top_right = [
        f"Mode: {runtime_status['active_mode'].upper()}",
        f"Requested: {runtime_status['requested_mode'].upper()}",
        f"Server: {'UP' if runtime_status['server_connected'] else 'DOWN'}",
        f"Camera: {camera_backend}{' (sim)' if camera_simulated else ''}",
        f"Frame: {display_background.upper()} · {render_count}",
    ]
    for index, line in enumerate(top_right):
        draw.text((width - 260, 30 + index * 16), line, fill=(244, 248, 252), font=font)

    _panel(draw, 18, 120, width - 36, height - 238)
    if runtime_status["active_mode"] in {"face", "both"}:
        draw.text((34, 136), "Face Zone", fill=(255, 255, 255), font=font)
        faces = runtime_status.get("detected_faces", [])
        if faces:
            for index, face in enumerate(faces[:3]):
                y = 164 + index * 48
                draw.rectangle((36, y, 132, y + 34), outline=(94, 234, 212), width=2)
                draw.text((146, y + 4), f"{face['name']} (seen {face['seen_count']}x)", fill=(240, 248, 255), font=font)
                last_seen = face.get("last_seen_at") or "never"
                draw.text((146, y + 20), f"Last seen: {last_seen}", fill=(241, 196, 120), font=font)
                summary = face.get("summary") or ""
                if summary:
                    draw.text((146, y + 34), summary[:48], fill=(255, 244, 140), font=font)
        else:
            draw.text((36, 172), "No live detections yet. Enrolled faces will appear here.", fill=(192, 215, 235), font=font)
    else:
        draw.text((34, 136), "Face recognition paused in AUDIO mode.", fill=(192, 215, 235), font=font)

    _panel(draw, 18, height - 102, width // 2 - 28, 84)
    draw.text((30, height - 94), "Reminders", fill=(255, 255, 255), font=font)
    if notes:
        for index, note in enumerate(notes[:3]):
            draw.text((30, height - 74 + index * 18), f"[!] {note.content}", fill=(245, 245, 245), font=font)
    else:
        draw.text((30, height - 74), "No active reminders", fill=(192, 215, 235), font=font)

    _panel(draw, width // 2, height - 102, width // 2 - 18, 84)
    draw.text((width // 2 + 12, height - 94), "Captions", fill=(255, 255, 255), font=font)
    if runtime_status["active_mode"] in {"audio", "both"}:
        draw.text(
            (width // 2 + 12, height - 74),
            (runtime_status.get("caption_text") or "Listening for speech...")[:72],
            fill=(192, 215, 235),
            font=font,
        )
    else:
        draw.text((width // 2 + 12, height - 74), "Captions hidden in FACE mode.", fill=(192, 215, 235), font=font)

    toast_text = runtime_status.get("toast_text")
    if toast_text:
        _panel(draw, width // 2 - 160, 86, 320, 40, strong=True)
        draw.text((width // 2 - 146, 100), str(toast_text)[:58], fill=(255, 255, 255), font=font)

    if runtime_status.get("launcher"):
        _panel(draw, width // 2 - 130, height // 2 - 28, 260, 52, strong=True)
        draw.text(
            (width // 2 - 112, height // 2 - 8),
            f"Launcher active: {runtime_status['launcher']}",
            fill=(255, 255, 255),
            font=font,
        )

    return frame


def _panel(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    strong: bool = False,
) -> None:
    fill = (9, 15, 22, 190 if strong else 164)
    outline = (92, 195, 255, 130)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=14, fill=fill, outline=outline, width=2)


def _dim_background(image: Image.Image, *, alpha: int) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, alpha))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
