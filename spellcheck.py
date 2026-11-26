from dataclasses import dataclass, field

import config as cfg


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@dataclass
class SpellResult:
    status: str                      # "ok" | "suggest" | "reject"
    suggestions: list = field(default_factory=list)
    message: str = ""


class SpellGate:
    """Typo guard built on pyspellchecker plus the game vocabulary."""

    def __init__(self, vocab):
        from spellchecker import SpellChecker
        self.vocab = {w.casefold() for w in vocab}
        self.spell = SpellChecker(distance=2)
        self.spell.word_frequency.load_words(list(self.vocab))

    def _known(self, w):
        return w in self.vocab or bool(self.spell.known([w]))

    def _suggest(self, w, limit=4):
        maxd = cfg.SPELLCHECK_MAX_EDIT_DISTANCE
        cands = set(self.spell.candidates(w) or [])
        cands |= {v for v in self.vocab if abs(len(v) - len(w)) <= maxd}
        cands = {c for c in cands if c != w and edit_distance(w, c) <= maxd}
        ranked = sorted(cands, key=lambda c: (edit_distance(w, c),
                                              c not in self.vocab,
                                              -self.spell.word_usage_frequency(c)))
        return ranked[:limit]

    def check(self, word, allow_proper=False):
        mode = cfg.SPELLCHECK_MODE
        if not cfg.ENABLE_SPELLCHECK or mode == "off":
            return SpellResult("ok")
        cw = word.casefold()
        if self._known(cw):
            return SpellResult("ok")
        # Capitalised input is treated as a proper noun: never flagged,
        # never lowercased (the caller keeps the original text).
        if allow_proper and word[:1].isupper():
            return SpellResult("ok")
        if mode == "strict":
            return SpellResult("reject", message=f"“{word}” isn’t a recognised word.")
        sugg = self._suggest(cw)
        return SpellResult("suggest", sugg) if sugg else SpellResult("ok")
