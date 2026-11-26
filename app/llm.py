"""Генерация названия микса через LLM.

Провайдер выбирается переменными окружения, потому что на GitHub Pages бэкенда
нет: фронт живёт на github.io, а FastAPI хостится отдельно (Render/Fly/VPS),
где локального Ollama обычно нет и быть не может.

  LLM_PROVIDER=ollama   (по умолчанию, для локальной разработки)
      OLLAMA_MODEL  по умолчанию qwen2.5:0.5b
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
import time
import uuid

import httpx
from ollama import chat as ollama_chat


def _ollama_chat_call(model: str, messages: list[dict], options: dict) -> dict:
    """Обёртка для вызова Ollama — мокается в тестах."""
    return ollama_chat(model=model, messages=messages, options=options)

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
    model_name = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    try:
        response = _ollama_chat_call(
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


# --- GigaChat (Сбер) ------------------------------------------------------
# Ключ авторизации (Basic) обменивается на access_token с жизнью 30 минут;
# сертификаты — НУЦ Минцифры, поэтому verify настраивается отдельно.

_GIGACHAT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_GIGACHAT_API_BASE = "https://gigachat.devices.sberbank.ru/api/v1"
_gigachat_cache = {"token": None, "expires_at": 0.0}


def _gigachat_verify():
    bundle = os.getenv("GIGACHAT_CA_BUNDLE", "").strip()
    if bundle:
        return bundle
    return os.getenv("GIGACHAT_VERIFY_SSL", "true").strip().lower() != "false"


def _gigachat_access_token() -> str:
    now = time.time()
    if _gigachat_cache["token"] and now < _gigachat_cache["expires_at"] - 60:
        return _gigachat_cache["token"]

    auth_key = os.getenv("GIGACHAT_AUTH_KEY", "").strip()
    if not auth_key:
        raise LLMUnavailable("LLM_PROVIDER=gigachat, но не задан GIGACHAT_AUTH_KEY")
    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip()

    try:
        resp = httpx.post(
            _GIGACHAT_OAUTH_URL,
            headers={
                "Authorization": f"Basic {auth_key}",
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={"scope": scope},
            verify=_gigachat_verify(),
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        _gigachat_cache["token"] = payload["access_token"]
        _gigachat_cache["expires_at"] = (
            float(payload.get("expires_at", (now + 25 * 60) * 1000)) / 1000
        )
        return _gigachat_cache["token"]
    except httpx.HTTPStatusError as exc:
        raise LLMUnavailable(
            f"GC OAuth ответил {exc.response.status_code}: {exc.response.text[:200]}"
        ) from exc
    except Exception as exc:
        raise LLMUnavailable(
            f"Не удалось получить токен GigaChat ({type(exc).__name__}: {exc})"
        ) from exc


def _chat_gigachat(messages: list[dict], temperature: float) -> str:
    model = os.getenv("GIGACHAT_MODEL", "GigaChat").strip()
    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    token = _gigachat_access_token()
    try:
        resp = httpx.post(
            f"{_GIGACHAT_API_BASE}/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 64,
            },
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            verify=_gigachat_verify(),
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as exc:
        raise LLMUnavailable(
            f"GigaChat ответил {exc.response.status_code}: {exc.response.text[:200]}"
        ) from exc
    except Exception as exc:
        raise LLMUnavailable(
            f"Ошибка обращения к GigaChat ({type(exc).__name__}: {exc})"
        ) from exc
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
    elif provider == "gigachat":
        title = _chat_gigachat(messages, temperature)
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
    if provider == "gigachat":
        auth_key = os.getenv("GIGACHAT_AUTH_KEY", "").strip()
        return {
            "provider": "gigachat",
            "model": os.getenv("GIGACHAT_MODEL", "GigaChat").strip(),
            "configured": bool(auth_key),
            "reason": None if auth_key else "не задан GIGACHAT_AUTH_KEY",
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
