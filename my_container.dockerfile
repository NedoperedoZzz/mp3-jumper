# Образ только для бэкенда: GitHub Pages отдаёт фронтенд, здесь живёт FastAPI.
# Python 3.11 — та же версия, что в CI (01-quality.yml), чтобы проверки
# и рантайм совпадали.
FROM python:3.11-slim
WORKDIR /app

# FFmpeg обязателен для /api/merge; libsndfile и rubberband нужны pyCrossfade.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 rubberband-cli \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем только то, что нужно серверу (тесты, доки и CI в образ не едут)
COPY app ./app
COPY static ./static

# Render и Fly передают назначенный порт переменной PORT
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
