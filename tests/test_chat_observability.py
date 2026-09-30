from __future__ import annotations

import json
import asyncio
from pathlib import Path

import httpx

from app import logging_config
from app.main import app


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())

    assert response.status_code == 200
    assert response.headers["x-request-id"].startswith("req-")
    assert response.headers["x-request-id"] == response.json()["correlation_id"]
    assert "x-response-time-ms" in response.headers
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True
    assert response_event["correlation_id"] == response.headers["x-request-id"]
    assert response_event["user_id_hash"]
    assert response_event["session_id"] == "session-01"
    assert response_event["feature"] == "qa"
    assert response_event["model"] == "claude-sonnet-4-5"
    assert response_event["env"] == "dev"


def test_chat_log_scrubs_pii_before_writing(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-02",
                    "session_id": "session-02",
                    "feature": "qa",
                    "message": "Contact test.person@example.com or 0901234567; CCCD 012345678901; card 4111 1111 1111 1111",
                },
            )

    response = asyncio.run(send_request())
    assert response.status_code == 200
    content = log_path.read_text(encoding="utf-8")
    assert "test.person@example.com" not in content
    assert "0901234567" not in content
    assert "012345678901" not in content
    assert "4111 1111 1111 1111" not in content
    assert "REDACTED_EMAIL" in content
    assert "REDACTED_PHONE_VN" in content
    assert "REDACTED_CCCD" in content
    assert "REDACTED_CREDIT_CARD" in content
