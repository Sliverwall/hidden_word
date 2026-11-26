"""All pacing, economy and tuning knobs for Hidden Word.

Nothing in game_engine.py, embeddings.py or server.py hard-codes these values;
they are read from this module at call time.
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

# ── Hand & word bank ────────────────────────────────────────────────────────
CARDS_PER_PLAYER = 5
WORD_BANK_PATH = os.path.join(_HERE, "words.csv")   # you supply this file
ALLOW_EXACT_WORD_HINT = True
ALLOW_PROPER_NOUN_HINTS = True

# ── Extra Word Tokens ───────────────────────────────────────────────────────
EXTRA_WORD_TOKENS_PER_GAME = 1
EXTRA_GUESSES_GRANTED = 2

# ── Spell check ─────────────────────────────────────────────────────────────
ENABLE_SPELLCHECK = True
SPELLCHECK_MODE = "suggest"        # "suggest" | "strict" | "off"
SPELLCHECK_MAX_EDIT_DISTANCE = 2

# ── Similarity & hint phase ────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.95
MAX_HINT_ATTEMPTS = 10
NEAREST_NEIGHBOR_ON_LIMIT = True
SEMANTIC_MODEL_NAME = "all-MiniLM-L6-v2"
# gensim-downloader name (downloaded once, then cached) OR a local path to a
# word2vec/GloVe file (.kv, .bin, .txt, .vec).
ASSOC_MODEL_NAME = "glove-wiki-gigaword-100"
REQUIRE_ASSOC_MODEL = True         # True: refuse to start without it (no silent degrade)
# Default for the in-game "Details" toggle (meaning/association % under each hint).
SHOW_SCORE_BREAKDOWN = False
EMBEDDING_ALPHA = 0.5              # weight of semantic vs. association signal

# Calibration of raw = ALPHA*s_sem + (1-ALPHA)*s_assoc  ->  final score.
# "piecewise": linear interpolation through CALIBRATION_ANCHORS (raw, score).
# "sigmoid":   1 / (1 + exp(-STEEPNESS * (raw - MIDPOINT))).
# Measured with MiniLM + glove-wiki-gigaword-100: related pairs have raw ~0.31-0.46,
# unrelated controls ~0.0-0.25. For a wider margin try ASSOC_MODEL_NAME =
# "glove-wiki-gigaword-300" (bigger download, cleaner associations).
# These defaults are a starting point: run `python test_similarity.py`
# and adjust until the benchmark pairs land where you want them.
CALIBRATION_MODE = "piecewise"
CALIBRATION_ANCHORS = [   # (raw blended cosine, final score)
    (0.00, 0.00),
    (0.15, 0.10),
    (0.25, 0.35),   # unrelated pairs (banana/tractor, dragon/fork) land here or below
    (0.30, 0.95),   # first raw value that counts as a hit
    (0.40, 0.98),
    (1.00, 1.00),
]
CALIBRATION_SIGMOID_MIDPOINT = 0.50
CALIBRATION_SIGMOID_STEEPNESS = 14.0

# ── Guessing & ramping scoring ─────────────────────────────────────────────
MAX_GUESS_ROUNDS = 4
FIRST_GUESS_CORRECT_POINTS = 2
SUBSEQUENT_GUESS_CORRECT_POINTS = 1
CLUE_GIVER_FAILED_GUESS_POINTS = [1, 2, 4, 6]

# ── Game end & LAN server ──────────────────────────────────────────────────
TARGET_WIN_SCORE = 12              # None disables score-based ending
MAX_ROUNDS = 3                     # None disables round-based ending
HOST = "0.0.0.0"
PORT = 8000
