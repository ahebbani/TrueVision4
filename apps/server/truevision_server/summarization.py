from __future__ import annotations

import re


def summarize_one_sentence(
    transcript: str,
    *,
    previous_summary: str | None = None,
    person_name: str | None = None,
    max_chars: int = 140,
) -> str:
    cleaned = re.sub(r"\s+", " ", transcript).strip()
    if not cleaned:
        base = "No conversation captured."
    else:
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        base = sentences[0].strip() or cleaned

    prefix = f"{person_name}: " if person_name else ""
    if previous_summary and base.lower() == previous_summary.strip().lower():
        prefix = f"{person_name}: still discussing " if person_name else "Still discussing "
        base = previous_summary.strip()

    return clamp_sentence(prefix + base, max_chars=max_chars)


def clamp_sentence(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[: max_chars - 1].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip(" ,;:-") + "…"
