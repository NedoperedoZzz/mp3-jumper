import os
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.audio import merge_audio
from app.llm import LLMUnavailable, generate_mix_title, llm_status
from app.metadata import extract_metadata, format_prompt_metadata

app = FastAPI()
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

# Фронтенд может лежать на GitHub Pages, а этот API — на Render/Fly/VPS.
# Тогда браузер идёт сюда с другого origin, и без CORS он получит отказ.
# По умолчанию CORS выключен (тот же источник), список включается переменной:
#   ALLOWED_ORIGINS="https://nedoperedozzz.github.io,http://127.0.0.1:8000"
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
]
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")


@app.get("/")
def read_root():
    return FileResponse("static/index.html")


@app.get("/api/health")
def health():
    """Проверка живости для фронтенда: работает ли склейка и настроена ли модель."""
    return {
        "status": "ok",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "cors_enabled": bool(ALLOWED_ORIGINS),
        "llm": llm_status(),
    }


@app.post("/api/merge")
async def merge_files(
    files: list[UploadFile] = File(...), use_smart: str = Form("false")
):
    session_id = str(uuid.uuid4())
    session_dir = TEMP_DIR / session_id
    session_dir.mkdir()

    saved_paths = []
    metadata_list = []

    for file in files:
        file_path = session_dir / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_paths.append(file_path)
        metadata_list.append(extract_metadata(file_path))

    output_path = session_dir / "mix.mp3"

    # Передаем флаг в функцию склейки
    is_smart = use_smart.lower() == "true"
    # Получаем тайм-коды
    timestamps_data = merge_audio(saved_paths, output_path, use_smart=is_smart)

    # Сохраняем их в файл
    import json

    (session_dir / "timestamps.json").write_text(
        json.dumps(timestamps_data, ensure_ascii=False), encoding="utf-8"
    )

    (session_dir / "meta.txt").write_text(
        format_prompt_metadata(metadata_list), encoding="utf-8"
    )

    return {"session_id": session_id, "status": "success"}


@app.post("/api/generate-title")
async def generate_title(session_id: str = Form(...), temperature: float = Form(0.7)):
    meta_file = TEMP_DIR / session_id / "meta.txt"
    if not meta_file.exists():
        return JSONResponse(status_code=404, content={"error": "Session not found"})

    prompt = meta_file.read_text(encoding="utf-8")
    try:
        title = generate_mix_title(prompt, temperature)
    except LLMUnavailable as exc:
        # Не притворяемся успехом: фронт покажет настоящую причину
        return JSONResponse(status_code=503, content={"error": str(exc)})
    return {"title": title}


@app.get("/api/timestamps/{session_id}")
def get_timestamps(session_id: str):
    ts_path = TEMP_DIR / session_id / "timestamps.json"
    if not ts_path.exists():
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return FileResponse(ts_path, media_type="application/json")


@app.get("/api/download/{session_id}")
def download_mix(session_id: str, filename: str = "my_mix.mp3"):
    mix_path = TEMP_DIR / session_id / "mix.mp3"
    if not mix_path.exists():
        return JSONResponse(status_code=404, content={"error": "Mix not found"})
    return FileResponse(
        mix_path,
        filename=filename,
        media_type="audio/mpeg",
        headers={"Accept-Ranges": "bytes"},  # <-- Добавляем поддержку перемотки
    )


# Раздаём статику и от корня, чтобы относительные пути в index.html
# (style.css, script.js, favicon.ico) работали одинаково локально через
# uvicorn и на GitHub Pages. Монтируем в самом конце: все /api/* маршруты
# зарегистрированы выше и имеют приоритет.
app.mount("/", StaticFiles(directory="static", html=True), name="static-root")
