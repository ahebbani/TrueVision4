from __future__ import annotations

from dataclasses import dataclass
import json
import os
from urllib import error, parse, request


WAKE_WORDS = ("assistant", "truevision")


@dataclass(slots=True)
class TelegramResult:
    sent: bool
    dry_run: bool
    message: str
    response: dict[str, object] | None = None


def extract_command_text(transcript: str) -> str:
    lowered = transcript.lower()
    for wake_word in WAKE_WORDS:
        token = lowered.find(wake_word)
        if token != -1:
            transcript = transcript[token + len(wake_word) :]
            break

    cleaned = transcript.strip(" .,!?:;")
    prefixes = (
        "send a telegram saying",
        "send telegram saying",
        "send a telegram",
        "send telegram",
        "telegram",
        "send",
    )
    lowered_cleaned = cleaned.lower()
    for prefix in prefixes:
        if lowered_cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip(" .,!?:;")
            lowered_cleaned = cleaned.lower()
    return cleaned


def send_telegram_message(message: str) -> TelegramResult:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return TelegramResult(sent=False, dry_run=True, message=message, response=None)

    body = parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = request.Request(url, data=body, method="POST")

    try:
        with request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        return TelegramResult(
            sent=False,
            dry_run=False,
            message=message,
            response={"error": str(exc)},
        )

    return TelegramResult(sent=True, dry_run=False, message=message, response=payload)
