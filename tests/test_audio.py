from pathlib import Path

from app.audio import merge_audio


def test_merge_audio_pycrossfade_success(mocker):
    """Проверяем, что при успехе pyCrossfade вызывается нужная функция."""
    # Мокаем получение длительности
    mocker.patch("app.audio.get_duration", return_value=180.0)

    # Принудительно включаем режим pycrossfade и создаем фейковые объекты
    mocker.patch("app.audio.HAS_PYCROSSFADE", True)
    mocker.patch("app.audio.Song", create=True)

    mocked_crossfade = mocker.patch(
        "app.audio.crossfade_multiple", create=True, return_value=b"fake_audio"
    )
    mocked_save = mocker.patch("app.audio.save_audio", create=True)

    files = [Path("track1.mp3"), Path("track2.mp3")]
    out = Path("out.mp3")

    merge_audio(files, out, use_smart=True)

    mocked_crossfade.assert_called_once()
    mocked_save.assert_called_once()


def test_merge_audio_fallback_on_error(mocker):
    """Если pyCrossfade падает, должен сработать FFmpeg-fallback."""
    mocker.patch("app.audio.get_duration", return_value=180.0)

    # Принудительно включаем режим pycrossfade
    mocker.patch("app.audio.HAS_PYCROSSFADE", True)
    mocker.patch("app.audio.Song", create=True)

    # Заставляем pyCrossfade выбросить ошибку
    mocker.patch(
        "app.audio.crossfade_multiple",
        create=True,
        side_effect=Exception("pyCrossfade error"),
    )

    # Мокаем FFmpeg (subprocess), чтобы он не запускался реально
    mocked_run = mocker.patch("app.audio.subprocess.run")

    files = [Path("track1.mp3"), Path("track2.mp3")]
    out = Path("out.mp3")

    merge_audio(files, out)

    # Проверяем, что сработал fallback
    mocked_run.assert_called_once()
