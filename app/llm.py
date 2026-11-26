"""Генерация названия микса через LLM.

Провайдер выбирается переменными окружения, потому что на GitHub Pages бэкенда
нет: фронт живёт на github.io, а FastAPI хостится отдельно (Render/Fly/VPS),
где локального Ollama обычно нет и быть не может.

  LLM_PROVIDER=ollama   (по умолчанию, для локальной разработки)
      OLLAMA_MODEL  по умолчанию llama3.2:1b
      OLLAMA_HOST   по умолчанию http://127.0.0.1:11434 (берёт библиотеку ollama)

  LLM_PROVIDER=openai   любой OpenAI-совместимый API:
      OpenRouter  https://openrouter.ai/api/v1
      Groq        https://api.groq.com/openai/v1
      DeepSeek    https://api.deepseek.com/v1
      Ollama Cloud https://ollama.com/...  (тоже совместим частично)
      LLM_BASE_URL, LLM_API_KEY (секрет!), LLM_MODEL — обязательны
      LLM_TIMEOUT   секунды, по умолчанию 60

Ошибки намеренно НЕ маскируются: раньше при падении модели возвращалась
строка "Midnight Mix (Fallback)" со статусом 200, и на опубликованном сайте
это выглядело как работающая ИИ-функция. Теперь бросается LLMUnavailable,
а маршрут /api/generate-title отвечает 503 с описанием причины.
"""

import os

import httpx
import ollama

SYSTEM_PROMPT = (
    "You are a creative electronic music DJ. Your task is to invent "
    "a short, catchy and atmospheric name for a music mix "
    "(1-3 words max). CRITICAL: DO NOT use any of the artist names "
    "or track titles provided in the input. Instead, create a "
    "completely new name that fits the vibe (e.g., 'Midnight Pulse', "
    "'Neon Dreams'). Output ONLY the mix name, no quotes, no extra words."
)

_CLOUD_PROVIDERS = ("openai", "openai_compatible")


class LLMUnavailable(RuntimeError):
    """Модель недоступна: нет конфигурации, сервер молчит или ответил не по формату."""


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "ollama").strip().lower()


def _clean(text: str) -> str:
    """Модели любят оборачивать название в кавычки или добавлять точку."""
    return text.strip().strip('"').strip("'").strip(".").strip()


def _chat_ollama(messages: list[dict], temperature: float) -> str:
    model_name = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    try:
        response = ollama.chat(
            model=model_name,
            messages=messages,
            options={
                "temperature": temperature,
                "num_predict": 25,  # Ограничиваем длину ответа
            },
        )
        content = response["message"]["content"]
    except LLMUnavailable:
        raise
    except Exception as exc:
        raise LLMUnavailable(
            f"Ollama ({model_name} @ "
            f"{os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434')}) недоступна: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return _clean(content)


def _chat_openai_compatible(messages: list[dict], temperature: float) -> str:
    base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "")
    model_name = os.getenv("LLM_MODEL", "")

    missing = [
        name
        for name, value in (
            ("LLM_BASE_URL", base_url),
            ("LLM_API_KEY", api_key),
            ("LLM_MODEL", model_name),
        )
        if not value
    ]
    if missing:
        raise LLMUnavailable(f"LLM_PROVIDER=openai, но не заданы: {', '.join(missing)}")

    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            json={
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 64,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as exc:
        raise LLMUnavailable(
            f"{base_url} ответил {exc.response.status_code}: "
            f"{exc.response.text[:200]}"
        ) from exc
    except Exception as exc:
        raise LLMUnavailable(
            f"Ошибка обращения к {base_url} ({type(exc).__name__}: {exc})"
        ) from exc

    if not isinstance(content, str):
        raise LLMUnavailable(
            f"Unexpected content type from {base_url}: {type(content).__name__}"
        )
    return _clean(content)


def generate_mix_title(prompt: str, temperature: float = 0.1) -> str:
    """Возвращает название микса или бросает LLMUnavailable с понятной причиной."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    provider = _provider()
    if provider in _CLOUD_PROVIDERS:
        title = _chat_openai_compatible(messages, temperature)
    elif provider == "ollama":
        title = _chat_ollama(messages, temperature)
    else:
        raise LLMUnavailable(
            f"Неизвестный LLM_PROVIDER={provider!r}; ожидался 'ollama' или 'openai'"
        )

    if not title:
        raise LLMUnavailable(f"{provider} вернул пустое название")
    return title


def llm_status() -> dict:
    """Диагностика для /api/health: фронт по ней показывает, жива ли ИИ-кнопка."""
    provider = _provider() or "ollama"
    if provider in _CLOUD_PROVIDERS:
        required = {
            "LLM_BASE_URL": os.getenv("LLM_BASE_URL", ""),
            "LLM_API_KEY": os.getenv("LLM_API_KEY", ""),
            "LLM_MODEL": os.getenv("LLM_MODEL", ""),
        }
        missing = [name for name, value in required.items() if not value]
        return {
            "provider": provider,
            "model": required["LLM_MODEL"] or None,
            "configured": not missing,
            "reason": None if not missing else f"не заданы: {', '.join(missing)}",
        }
    if provider != "ollama":
        return {
            "provider": provider,
            "model": None,
            "configured": False,
            "reason": f"неизвестный LLM_PROVIDER={provider!r}",
        }
    return {
        "provider": "ollama",
        "model": os.getenv("OLLAMA_MODEL", "llama3.2:1b"),
        "configured": True,
        "reason": None,
    }
