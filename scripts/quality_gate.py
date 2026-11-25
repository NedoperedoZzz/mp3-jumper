"""Собирает результаты нескольких независимых проверок качества."""

import json
import subprocess
from pathlib import Path

CHECKS = [
    ("lint", ["python", "-m", "ruff", "check", "."]),
    ("format", ["python", "-m", "ruff", "format", "--check", "."]),
    ("tests", ["python", "-m", "pytest", "-q"]),
    ("hygiene", ["python", "scripts/repo_hygiene.py"]),
    ("ai-declaration", ["python", "scripts/check_ai_declaration.py"]),
]


def main() -> int:
    results = []
    for title, command in CHECKS:
        print(f"\n===== {title}: {' '.join(command)} =====", flush=True)
        completed = subprocess.run(command, check=False)
        results.append({"check": title, "exit_code": completed.returncode})
        print(f"[{title}] exit_code={completed.returncode}", flush=True)

    failed = [item["check"] for item in results if item["exit_code"] != 0]
    report = {"status": "FAIL" if failed else "PASS", "checks": results}
    output = Path("reports/quality.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nИТОГ: {report['status']}; провалены: {failed}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
