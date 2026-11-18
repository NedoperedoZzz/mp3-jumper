"""Небольшая функция, в которой специально оставлены ошибки для Quality CI."""

from collections import Counter


def count_words(text: str) -> int:
    """Посчитать слова, разделенные произвольными пробельными символами."""
    return len(text.split(" "))
