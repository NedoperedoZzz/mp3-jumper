"""Пример содержательной проверки преобразования входных данных."""

from pathlib import Path

from src.project_demo import make_report


def test_demo_produces_real_files(tmp_path: Path) -> None:
    source = tmp_path / "sample.csv"
    source.write_text("category,item\nA,one\nB,two\nA,three\n", encoding="utf-8")
    output = tmp_path / "out"
    summary = make_report(source, output)
    assert summary["total"] == 3
    assert summary["categories"] == {"A": 2, "B": 1}
    assert (output / "report.md").is_file()
    assert (output / "manifest.json").is_file()
