import csv
import os

import config as cfg


class WordBankError(RuntimeError):
    pass


def load_words(path=None):
    """Read the first column of a CSV (an optional 'word' header is skipped)."""
    path = path or cfg.WORD_BANK_PATH
    if not os.path.isfile(path):
        raise WordBankError(
            f"Word bank not found at '{path}'. Create it (one word per row) or "
            f"change WORD_BANK_PATH in config.py.")
    words, seen = [], set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if not row:
                continue
            w = row[0].strip()
            if not w or (not words and not seen and w.casefold() == "word"):
                continue
            if w.casefold() not in seen:
                seen.add(w.casefold())
                words.append(w.casefold())
    if not words:
        raise WordBankError(f"Word bank '{path}' is empty.")
    return words
