"""Учебный пример: превращаем CSV в артефакты GitVerse CI/CD.

Это демонстрационная заготовка. Она НЕ считается самостоятельным проектом.
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def make_report(source: Path, output: Path) -> dict:
    """Собрать простую сводку по категориям и записать файлы результата."""
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"category", "item"}.issubset(reader.fieldnames or []):
            raise ValueError("Нужны столбцы category и item")
        records = list(reader)

    if not records:
        raise ValueError("Входной CSV пуст")

    counters = Counter(row["category"] for row in records)
    summary = {
        "source": source.name,
        "total": len(records),
        "categories": dict(sorted(counters.items())),
    }

    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rows = ["# Пример отчета", "", f"Всего записей: {len(records)}", ""]
    rows += [f"- {category}: {count}" for category, count in sorted(counters.items())]
    (output / "report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    # В манифесте намеренно стоит явный маркер заготовки.
    # Он помогает преподавателю распознать неизмененный демонстрационный проект.
    manifest = {
        "project": "TEMPLATE_DEMO_REPLACE_ME",
        "files": ["summary.json", "report.md"],
        "record_count": len(records),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Собрать пример отчета из CSV")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = make_report(args.input, args.output)
    print(f"Пример: обработано записей: {summary['total']}")


if __name__ == "__main__":
    main()
