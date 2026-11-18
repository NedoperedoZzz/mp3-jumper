"""Тесты специально выявляют ошибки в стартовом исходнике."""

from src.starter import count_words


def test_multiple_spaces() -> None:
    assert count_words("один   два") == 2


def test_empty_string() -> None:
    assert count_words("") == 0


def test_tabs_and_newlines() -> None:
    assert count_words("первый\tвторой\nтретий") == 3
