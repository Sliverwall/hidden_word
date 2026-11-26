import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from game_engine import Game  # noqa: E402

VOCAB = [f"wd{i:03d}" for i in range(60)] + ["apple", "hot", "warm", "cold"]


class FakeScorer:
    """Deterministic stand-in for the ML scorer."""

    def __init__(self):
        self.table = {}
        self.default = 0.30
        self.near = ("wd059", {"sem": .5, "assoc": .5, "raw": .5, "score": .60})

    def score(self, hidden, hint):
        s = 1.0 if hint == hidden else self.table.get(hint, self.default)
        return {"sem": s, "assoc": s, "raw": s, "score": s}

    def nearest(self, hidden, exclude=()):
        return self.near


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    for k, v in dict(
        CARDS_PER_PLAYER=5, ALLOW_EXACT_WORD_HINT=True, ALLOW_PROPER_NOUN_HINTS=True,
        EXTRA_WORD_TOKENS_PER_GAME=1, EXTRA_GUESSES_GRANTED=2, ENABLE_SPELLCHECK=True,
        SPELLCHECK_MODE="off", SPELLCHECK_MAX_EDIT_DISTANCE=2, SIMILARITY_THRESHOLD=0.95,
        MAX_HINT_ATTEMPTS=10, NEAREST_NEIGHBOR_ON_LIMIT=True, MAX_GUESS_ROUNDS=4,
        FIRST_GUESS_CORRECT_POINTS=2, SUBSEQUENT_GUESS_CORRECT_POINTS=1,
        CLUE_GIVER_FAILED_GUESS_POINTS=[1, 2, 4, 6], TARGET_WIN_SCORE=None,
        MAX_ROUNDS=None, SHOW_SCORE_BREAKDOWN=False).items():
        monkeypatch.setattr(config, k, v)


@pytest.fixture
def scorer():
    s = FakeScorer()
    s.table.update({"close": 0.97, "far": 0.20, "close2": 0.96})
    return s


@pytest.fixture
def make_game(scorer):
    def _make(n=3, hidden="apple"):
        g = Game(VOCAB, scorer, rng=random.Random(7))
        for i in range(n):
            g.add_player(f"P{i}")
        g.start(g.players[0].pid)
        g.giver.hand[0] = hidden
        g.select_word(g.giver.pid, hidden)
        return g
    return _make


def lock_hint(g, word="close"):
    g.submit_hint(g.giver.pid, word)


def guess_all(g, word, skip=()):
    for p in g.players:
        if p is not g.giver and p.pid not in skip:
            g.submit_guess(p.pid, [word])
