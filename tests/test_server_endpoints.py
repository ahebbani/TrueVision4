from __future__ import annotations

from fastapi.testclient import TestClient

from truevision_server.app import create_app
from truevision_server.summarization import summarize_one_sentence
from truevision_server.telegram import extract_command_text


def test_extract_command_text_strips_wake_word_and_prefix() -> None:
    command = extract_command_text(
        "Hey assistant, send a telegram saying I'll be five minutes late."
    )
    assert command == "I'll be five minutes late"


def test_summarize_one_sentence_clamps_output() -> None:
    summary = summarize_one_sentence(
        "We reviewed the roadmap and moved the release by two weeks. We also discussed marketing.",
        person_name="Alex",
        max_chars=38,
    )
    assert summary.startswith("Alex:")
    assert len(summary) <= 38


def test_server_endpoints_work_without_external_services(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with TestClient(create_app()) as client:
        summarize = client.post(
            "/summarize",
            json={
                "transcript": "We discussed the schedule and agreed to meet Tuesday.",
                "person_name": "Maya",
                "max_chars": 80,
            },
        )
        assert summarize.status_code == 200
        assert summarize.json()["source"] == "local"

        telegram = client.post(
            "/telegram",
            json={"command": "Assistant, send telegram saying hello team"},
        )
        assert telegram.status_code == 200
        assert telegram.json()["dry_run"] is True
        assert telegram.json()["message"] == "hello team"

        telegram_llm = client.post(
            "/telegram_llm",
            json={"command": "TrueVision, send a telegram saying meeting moved to noon"},
        )
        assert telegram_llm.status_code == 200
        assert telegram_llm.json()["model"] == "fallback-cleanup"

        health = client.get("/health")
        assert health.status_code == 200
        assert "summarize" in health.json()["services"]