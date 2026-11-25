"""Минимальная проверка заполнения обязательной декларации моделей ИИ.

Не пытается определить, какие модели фактически использовал студент.
"""

import re
from pathlib import Path

DECLARATION = Path("AI_MODELS.md")
ALLOWED_STATUSES = {"ИСПОЛЬЗОВАЛ", "НЕ ИСПОЛЬЗОВАЛ"}


def main() -> int:
    if not DECLARATION.is_file():
        print("[FAIL] Отсутствует обязательный файл AI_MODELS.md")
        return 1

    content = DECLARATION.read_text(encoding="utf-8")
    match = re.search(r"^\*\*Статус:\*\*\s*(.+?)\s*$", content, re.MULTILINE)
    status = match.group(1).strip() if match else ""
    if status not in ALLOWED_STATUSES:
        print("[FAIL] Укажите в AI_MODELS.md: ИСПОЛЬЗОВАЛ или НЕ ИСПОЛЬЗОВАЛ")
        return 1

    if "| ЗАПОЛНИТЬ |" in content:
        print("[FAIL] Удалите незаполненную строку-пример из таблицы моделей")
        return 1

    if status == "ИСПОЛЬЗОВАЛ":
        rows = [line for line in content.splitlines() if line.startswith("|")]
        # Первая строка — заголовок, вторая — разделители колонок.
        if len(rows) < 3:
            print("[FAIL] Перечислите использованные модели в таблице")
            return 1
    print("[OK] Декларация моделей ИИ оформлена (содержание проверяет преподаватель)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
