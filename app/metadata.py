from pathlib import Path

from mutagen.easyid3 import EasyID3


def extract_metadata(file_path: Path) -> dict:
    """Извлекает исполнителя и название из ID3-тегов."""
    try:
        audio = EasyID3(file_path)
        artist = audio.get("artist", ["Unknown Artist"])[0]
        title = audio.get("title", ["Unknown Track"])[0]
        return {"artist": artist, "title": title}
    except Exception:
        return {"artist": "Unknown Artist", "title": file_path.stem}


def format_prompt_metadata(metadata_list: list[dict]) -> str:
    """Формирует компактный промпт для LLM (без лишних токенов)."""
    tracks = [f"{m['artist']} - {m['title']}" for m in metadata_list]
    prompt = "Список треков для микса:\n" + "\n".join(tracks[:20])
    return prompt
