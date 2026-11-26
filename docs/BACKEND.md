# Бэкенд для опубликованного сайта (GitHub Pages + внешний FastAPI)

Опубликованная на GitHub Pages страница — это **витрина**: Pages раздаёт только файлы
(`index.html`, `style.css`, `script.js`), никакой Python там не выполняется. Поэтому
`/api/merge` и `/api/generate-title` на `https://<user>.github.io/mp3-jumper/` дают 404,
а кнопка «✨ Сгенерировать ИИ» вообще не стреляет запросом: она выходит на
`if (!currentSessionId) return`, а `currentSessionId` появляется только из успешного
ответа `/api/merge`.

Чтобы фичи заработали на опубликованной странице, бэкенд поднимается отдельно, а во
фронтенде прописывается его адрес:

```
GitHub Pages (фронт)  ──HTTPS + CORS──►  Render/Fly (FastAPI, FFmpeg)  ──HTTPS──►  облачная LLM
```

## 1. Кто считает LLM

Генерация названия живёт в `app/llm.py` и вызывается **на стороне сервера**. Модель
переключается переменными окружения, код от этого не меняется:

| Режим | Переменные | Где считается | Когда выбрать |
|---|---|---|---|
| `LLM_PROVIDER=ollama` (по умолчанию) | `OLLAMA_MODEL` (llama3.2:1b), `OLLAMA_HOST` | твоя машина, где запущен `ollama serve` | локальная разработка, `uvicorn` на ноутбуке |
| `LLM_PROVIDER=openai` | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | провайдер API | любой хостинг, включая Render/Fly free |

`openai` — это «любой OpenAI-совместимый `/chat/completions`», например:

| Провайдер | `LLM_BASE_URL` | пример `LLM_MODEL` |
|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | `meta-llama/llama-3.2-1b-instruct:free` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.2-1b-preview` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |

Локальный Ollama на хостинге заведётся только если в контейнере есть сам Ollama и
модель (~1,3 ГБ веса, 2–4 ГБ RAM на инференс). На бесплатном тарифе Render (512 MB)
это невозможно, поэтому для опубликованной версии — облачный API. **Мощности твоего ПК
при этом не участвуют**: браузер шлёт JSON на бэкенд, а тензодельную работу делает
провайдер. Если хочется именно «на своём железе» — это вариант `ollama` + локальный
`uvicorn`, либо Pages-страница с `window.MP3_API_BASE = "http://127.0.0.1:8000"`
(Chrome разрешает запросы с https-страницы на localhost; работает только там, где
поднят бэкенд).

Отдельно: раньше при недоступной модели возвращалась строка
`"Midnight Mix (Fallback)"` со статусом 200 — на опубликованном сайте это выглядело как
работающая ИИ-функция. Теперь `app/llm.py` бросает `LLMUnavailable`, а
`POST /api/generate-title` отвечает **503 с текстом причины**. Проверить можно так:

```bash
curl -s https://<backend>.onrender.com/api/health | python3 -m json.tool
# {"status":"ok","ffmpeg":true,"cors_enabled":true,
#  "llm":{"provider":"openai","model":"meta-llama/llama-3.2-1b-instruct:free","configured":true,"reason":null}}
```

Если `configured: false`, в `reason` будет список недостающих переменных — фронт
красиво покажет это в плашке статуса вместо загадочного «Произошла ошибка».

## 2. Деплой на Render (основной путь, blueprint уже в репо)

1. Заведи ключ провайдера (например, OpenRouter → `sk-or-...`).
2. Render → **New → Blueprint** → выбери `NedoperedoZzz/mp3-jumper`. Render подхватит
   `render.yaml`: сервис `mp3-jumper-api` из `my_container.dockerfile`.
3. На шаге настроек впиши `LLM_API_KEY` (в `render.yaml` он помечен `sync: false` —
   секрет не хранится в git).
4. После деплоя проверь `https://<service>.onrender.com/api/health`.
   Если Render не предлагает free-план для `runtime: docker`, в `render.yaml` есть
   закомментированный вариант `runtime: python` с теми же переменными.
5. Пропиши адрес во фронтенде: в `static/index.html`

   ```js
   window.MP3_API_BASE = "https://<service>.onrender.com";
   ```

   и запушь в `master` — `03-pages.yml` пересоберёт Pages сам (триггер — изменения в `static/`).

Переменные окружения, которые читает приложение:

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `ALLOWED_ORIGINS` | список origin'ов через запятую, которым разрешён CORS | пусто = CORS выключен |
| `LLM_PROVIDER` | `ollama` или `openai` | `ollama` |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | облачной режим | — |
| `LLM_TIMEOUT` | секунды на запрос к модели | `60` |
| `OLLAMA_MODEL` | имя модели в Ollama | `llama3.2:1b` |
| `PORT` | порт uvicorn (ставит хостинг) | `8000` |

### Что нужно знать про бесплатный тариф

- **Cold start.** Через ~15 минут простоя сервис засыпает, первый запрос — до минуты.
  Для демо это ощутимо: `script.js` честно покажет ошибку, повторный клик помогает.
- **`temp/` эфемерный.** Готовые миксы живут только до перезапуска/пересборки, ссылка
  `/api/download/<session_id>` после рестарта отдаёт 404. Для долговечности нужен
  диск или object storage (S3-совместимый).
- **FFmpeg есть** — он ставится в образе, так что `/api/merge` на free-тарифе работает;
  «умный» режим (pyCrossfade) на больших файлах упрётся в 512 MB RAM — для хостинга
  лучше оставлять быстрый режим.

## 3. Альтернатива: Fly.io

```bash
fly launch --dockerfile my_container.dockerfile --no-deploy
fly secrets set LLM_PROVIDER=openai LLM_BASE_URL=https://openrouter.ai/api/v1 \
                LLM_MODEL=meta-llama/llama-3.2-1b-instruct:free LLM_API_KEY=sk-or-...
fly deploy
fly ips allocate-v6   # если нужен IPv6
```

В `ALLOWED_ORIGINS` — `https://nedoperedozzz.github.io`. `internal_port` в `fly.toml`
должен быть `8000` (образ слушает `${PORT}`).

## 4. Быстрая самопроверка после деплоя

```bash
BASE=https://<service>.onrender.com
curl -s "$BASE/api/health"                      # status/ffmpeg/llm
curl -s -X POST "$BASE/api/merge" -F "files=@test1.mp3" -F "files=@test2.mp3" -F "use_smart=false"
curl -s -X POST "$BASE/api/generate-title" -F "session_id=<из предыдущего ответа>"
# Проверка CORS с origin Pages:
curl -s -o /dev/null -D - -X OPTIONS "$BASE/api/merge" \
     -H "Origin: https://nedoperedozzz.github.io" \
     -H "Access-Control-Request-Method: POST" | grep -i access-control
```

Ожидаем: `access-control-allow-origin: https://nedoperedozzz.github.io`. Если строки нет —
`ALLOWED_ORIGINS` не задан или адрес Pages написан с `www`/без слэша иначе.

## 5. Тесты

`tests/test_llm.py` и `tests/test_api_llm.py` покрывают оба провайдера, отсутствие
конфигурации, HTTP-ошибку провайдера и то, что 503 возвращается вместо маскирующего
fallback'а. `pytest tests/ -q` прогоняет всё без сети (транспорт замокан).
