import pytest

from app.llm import LLMUnavailable, generate_mix_title, llm_status


def test_generate_mix_title_success(mocker):
    """Проверяем, что название корректно извлекается из ответа Ollama."""
    # Мокаем функцию chat из библиотеки ollama
    mock_chat = mocker.patch("app.llm.ollama_chat")

    # Имитируем ответ от Ollama
    mock_chat.return_value = {
        "message": {"content": '"Neon Nights"'},  # Модель добавила кавычки
        "done": True,
    }

    title = generate_mix_title("Artist - Track", temperature=0.8)

    assert title == "Neon Nights"  # Кавычки должны быть удалены
    mock_chat.assert_called_once()


def test_generate_mix_title_raises_when_ollama_down(mocker):
    """LLM не должна притворяться успешной: вместо fallback — явная ошибка.

    Иначе на опубликованном сайте константа "Midnight Mix (Fallback)"
    выглядела бы как реально сгенерированное ИИ название.
    """
    mocker.patch("app.llm.ollama_chat", side_effect=Exception("Connection error"))

    with pytest.raises(LLMUnavailable) as err:
        generate_mix_title("Artist - Track")

    assert "Ollama" in str(err.value)
    assert "Connection error" in str(err.value)


def test_generate_mix_title_rejects_empty_answer(mocker):
    """Пустой ответ модели — это тоже ошибка, а не название."""
    mocker.patch("app.llm.ollama_chat", return_value={"message": {"content": '  "'}})

    with pytest.raises(LLMUnavailable):
        generate_mix_title("Artist - Track")


def test_generate_mix_title_cloud_provider(mocker, monkeypatch):
    """LLM_PROVIDER=openai: идём в OpenAI-совместимый API, Ollama не трогаем."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1/")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_MODEL", "some-cloud-1b")

    ollama_mock = mocker.patch("app.llm.ollama_chat")
    post = mocker.patch("app.llm.httpx.post")
    post.return_value.json.return_value = {
        "choices": [{"message": {"content": "'Midnight Pulse'"}}]
    }
    title = generate_mix_title("Artist - Track", temperature=0.5)
    assert title == "Midnight Pulse"
    ollama_mock.assert_not_called()

    args, kwargs = post.call_args
    assert args[0] == "https://api.example.com/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer secret-key"
    assert kwargs["json"]["model"] == "some-cloud-1b"


def test_generate_mix_title_cloud_requires_configuration(mocker, monkeypatch):
    """Без ключа/адреса облачный режим сразу сообщает, чего не хватает."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "some-cloud-1b")
    post = mocker.patch("app.llm.httpx.post")

    with pytest.raises(LLMUnavailable) as err:
        generate_mix_title("Artist - Track")

    assert "LLM_BASE_URL" in str(err.value) and "LLM_API_KEY" in str(err.value)
    post.assert_not_called()


def test_generate_mix_title_cloud_http_error(mocker, monkeypatch):
    """4xx/5xx от облачного API превращается в LLMUnavailable с кодом ответа."""
    import httpx

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_MODEL", "some-cloud-1b")

    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(401, text="invalid api key", request=request)
    mocker.patch(
        "app.llm.httpx.post",
        side_effect=httpx.HTTPStatusError("401", request=request, response=response),
    )

    with pytest.raises(LLMUnavailable) as err:
        generate_mix_title("Artist - Track")

    assert "401" in str(err.value)


def test_generate_mix_title_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "telepathy")

    with pytest.raises(LLMUnavailable) as err:
        generate_mix_title("Artist - Track")

    assert "telepathy" in str(err.value)


def test_llm_status_reports_cloud_config(monkeypatch):
    """/api/health опирается на llm_status: незаполненный ключ виден сразу."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "some-cloud-1b")

    status = llm_status()

    assert status["provider"] == "openai"
    assert status["configured"] is False
    assert "LLM_API_KEY" in status["reason"]


def test_llm_status_defaults_to_ollama(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    status = llm_status()

    assert status == {
        "provider": "ollama",
        "model": "llama3.2:1b",
        "configured": True,
        "reason": None,
    }
