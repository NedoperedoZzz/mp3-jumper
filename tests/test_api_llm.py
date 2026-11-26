"""Проверка HTTP-поведения ИИ-маршрута: честные коды вместо «всё хорошо»."""

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.llm import LLMUnavailable
from app.main import TEMP_DIR, app

client = TestClient(app)


def test_health_reports_llm_config():
    """Фронтенд по /api/health решает, активна ли кнопка «Сгенерировать ИИ»."""
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert set(body["llm"]) == {"provider", "model", "configured", "reason"}


def test_generate_title_unknown_session():
    response = client.post("/api/generate-title", data={"session_id": "нет-такой"})

    assert response.status_code == 404


def test_generate_title_returns_503_when_llm_down(monkeypatch):
    """Модель упала -> 503 с причиной, а не 200 с «Midnight Mix (Fallback)»."""
    session_id = str(uuid.uuid4())
    session_dir = TEMP_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "meta.txt").write_text("Artist - Track", encoding="utf-8")

    def boom(prompt, temperature=0.1):
        raise LLMUnavailable("Ollama недоступна: Connection error")

    monkeypatch.setattr("app.main.generate_mix_title", boom)
    try:
        response = client.post("/api/generate-title", data={"session_id": session_id})

        assert response.status_code == 503
        assert "Ollama" in response.json()["error"]
    finally:
        shutil.rmtree(session_dir, ignore_errors=True)


def test_generate_title_ok(monkeypatch):
    session_id = str(uuid.uuid4())
    session_dir = TEMP_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "meta.txt").write_text("Artist - Track", encoding="utf-8")

    monkeypatch.setattr(
        "app.main.generate_mix_title", lambda prompt, temperature=0.1: "Neon Pulse"
    )
    try:
        response = client.post("/api/generate-title", data={"session_id": session_id})

        assert response.status_code == 200
        assert response.json() == {"title": "Neon Pulse"}
    finally:
        shutil.rmtree(session_dir, ignore_errors=True)


def test_unused_path_marker():
    """Защита от тихой регрессии: temp-каталог создаётся при импорте приложения."""
    assert Path(TEMP_DIR).is_dir()


@pytest.mark.parametrize("provider", ["ollama", "openai"])
def test_health_accepts_both_providers(provider, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", provider)

    assert client.get("/api/health").json()["llm"]["provider"] == provider
