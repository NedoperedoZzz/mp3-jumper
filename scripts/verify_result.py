"""Демонстрация того, как второй job потребляет артефакт первого."""

import json
import sys
from pathlib import Path


def verify(directory: Path) -> None:
    manifest_file = directory / "manifest.json"
    if not manifest_file.is_file():
        raise ValueError("Отсутствует manifest.json в скачанном артефакте")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("В манифесте отсутствует список файлов")
    for name in files:
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError(f"Небезопасное имя файла: {name!r}")
        if not (directory / name).is_file():
            raise ValueError(f"Артефакт ссылается на несуществующий файл: {name}")
    print("Артефакт успешно передан между jobs")
    print(f"Проект: {manifest.get('project')}")
    print(f"Файлы: {', '.join(files)}")


if __name__ == "__main__":
    try:
        verify(Path(sys.argv[1]))
    except (IndexError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"Ошибка проверки артефакта: {error}", file=sys.stderr)
        raise SystemExit(1) from error
