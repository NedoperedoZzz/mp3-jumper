from app.llm import generate_mix_title


def test_generate_mix_title_success(mocker):
    """Проверяем, что название корректно извлекается из ответа Ollama."""
    # Мокаем функцию chat из библиотеки ollama
    mock_chat = mocker.patch("app.llm.ollama.chat")

    # Имитируем ответ от Ollama
    mock_chat.return_value = {
        "message": {"content": '"Neon Nights"'},  # Модель добавила кавычки
        "done": True,
    }

    title = generate_mix_title("Artist - Track", temperature=0.8)

    assert title == "Neon Nights"  # Кавычки должны быть удалены
    mock_chat.assert_called_once()


def test_generate_mix_title_fallback(mocker):
    """Проверяем, что при ошибке возвращается fallback."""
    # Имитируем падение Ollama
    mocker.patch("app.llm.ollama.chat", side_effect=Exception("Connection error"))

    title = generate_mix_title("Artist - Track")

    assert title == "Midnight Mix (Fallback)"
