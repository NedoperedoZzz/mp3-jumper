"""Минимальная гигиена файлов, попавших под Git.

Не пытается заменить поиск секретов и антивирусный сканер.
"""

import subprocess
import sys
from pathlib import Path

BAD_NAMES = {".env", "id_rsa", "id_ed25519"}
BAD_SUFFIXES = {".pyc", ".p12", ".pfx", ".pem", ".key"}
BAD_DIRECTORIES = {"__pycache__", ".venv", "venv", ".pytest_cache"}
LIMIT_BYTES = 5 * 1024 * 1024


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print("Не удалось получить список отслеживаемых Git файлов", file=sys.stderr)
        return 2

    problems = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        filename = raw.decode("utf-8", errors="replace")
        path = Path(filename)
        if (
            path.name in BAD_NAMES
            or path.suffix.lower() in BAD_SUFFIXES
            or BAD_DIRECTORIES.intersection(path.parts)
        ):
            problems.append(f"Не следует хранить в Git: {filename}")
        if path.exists() and path.stat().st_size > LIMIT_BYTES:
            problems.append(f"Большой отслеживаемый файл (>5 МБ): {filename}")

    for message in problems:
        print(f"[WARN] {message}")
    if problems:
        return 1
    print("Проверка гигиены репозитория пройдена")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
