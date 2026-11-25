import shutil
import subprocess
from pathlib import Path

# Пытаемся импортировать pycrossfade, если она установлена
try:
    from pycrossfade.song import Song
    from pycrossfade.transition import crossfade_multiple
    from pycrossfade.utils import save_audio

    HAS_PYCROSSFADE = True
except ImportError:
    HAS_PYCROSSFADE = False


def get_duration(file_path: Path) -> float:
    """Получает длительность аудиофайла в секундах через ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def _merge_with_pycrossfade(
    input_files: list[Path], output_file: Path, crossfade_sec: float
) -> bool:
    """Пытается склеить треки через pyCrossfade (beat-matching + EQ)."""
    if not HAS_PYCROSSFADE:
        return False

    try:
        song_list = [Song(str(f)) for f in input_files]
        min_duration = min(get_duration(f) for f in input_files)
        safe_fade = min(crossfade_sec, min_duration / 2)

        output_audio = crossfade_multiple(
            song_list, len_crossfade=safe_fade, len_time_stretch=safe_fade
        )
        save_audio(output_audio, str(output_file))
        return True
    except Exception as e:
        print(f"[pyCrossfade fallback] {type(e).__name__}: {e}")
        return False


def _merge_with_ffmpeg_fallback(
    input_files: list[Path], output_file: Path, crossfade_sec: float
):
    """Надёжный fallback через чистый FFmpeg, если pyCrossfade не сработал."""
    min_duration = min(get_duration(f) for f in input_files)
    safe_crossfade = min(crossfade_sec, min_duration / 2)

    cmd = ["ffmpeg", "-y"]
    for f in input_files:
        cmd.extend(["-i", str(f)])

    filter_parts = []
    for i in range(1, len(input_files)):
        in1 = f"[{i-1}:a]" if i == 1 else f"[a{i-1}]"
        in2 = f"[{i}:a]"
        out = f"[a{i}]"
        filter_parts.append(
            f"{in1}{in2}acrossfade=d={safe_crossfade:.2f}:c1=tri:c2=tri{out}"
        )

    filter_str = ";".join(filter_parts)
    cmd.extend(
        [
            "-filter_complex",
            filter_str,
            "-map",
            f"[a{len(input_files)-1}]",
            str(output_file),
        ]
    )
    subprocess.run(cmd, check=True, capture_output=True)


def merge_audio(
    input_files: list[Path],
    output_file: Path,
    crossfade_sec: float = 3.0,
    use_smart: bool = False,
) -> list[dict]:
    if not input_files:
        raise ValueError("Список файлов пуст")

    # Считаем тайм-коды
    timestamps = []
    current_time = 0.0
    for i, f in enumerate(input_files):
        duration = get_duration(f)
        # Защита от слишком коротких треков
        actual_crossfade = (
            min(crossfade_sec, duration / 2) if i < len(input_files) - 1 else 0
        )

        end_time = current_time + duration
        timestamps.append(
            {
                "track": f.name,
                "start": round(current_time, 1),
                "end": round(end_time, 1),
            }
        )

        # Для следующего трека отнимаем время перехода
        current_time = end_time - actual_crossfade

    if len(input_files) == 1:
        shutil.copyfile(input_files[0], output_file)
        return timestamps

    if use_smart:
        success = _merge_with_pycrossfade(input_files, output_file, crossfade_sec)
        if success:
            return timestamps

    _merge_with_ffmpeg_fallback(input_files, output_file, crossfade_sec)
    return timestamps
