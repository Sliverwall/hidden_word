"""Pure game logic. All tuning comes from config.py (read at call time)."""
import random
import re
import uuid
from dataclasses import dataclass, field

import config as cfg
from spellcheck import SpellGate

WORD_RE = re.compile(r"^[^\W\d_][\w'\-]*$", re.UNICODE)


class GameError(Exception):
    pass


def norm(w):
    return w.strip().casefold()


@dataclass
class Player:
    pid: str
    name: str
    score: int = 0
    tokens: int = 0
    hand: list = field(default_factory=list)
    connected: bool = True


class Game:
    def __init__(self, vocab, scorer, spell=None, rng=None):
        self.vocab = [norm(w) for w in vocab]
        self.scorer = scorer
        self.spell = spell or SpellGate(self.vocab)
        self.rng = rng or random.Random()
        self.players = []
        self.phase = "lobby"
        self.giver_idx = 0
        self.rounds_played = 0
        self.last_turn = None
        self.winners = []
        self.end_reason = None
        self.first_pid = None      # who opened the previous match
        self._reset_turn()

    # ── players ───────────────────────────────────────────────────────────
    def _p(self, pid):
        for p in self.players:
            if p.pid == pid:
                return p
        raise GameError("Unknown player.")

    @property
    def giver(self):
        return self.players[self.giver_idx]

    def add_player(self, name):
        name = " ".join(name.split())[:20]
        if not name:
            raise GameError("Enter a name.")
        if self.phase != "lobby":
            raise GameError("A game is in progress. Join when it ends.")
        if any(norm(p.name) == norm(name) for p in self.players):
            raise GameError("That name is taken.")
        p = Player(uuid.uuid4().hex, name)
        self.players.append(p)
        return p

    def remove_player(self, pid):
        self.players = [p for p in self.players if p.pid != pid]

    def has_player(self, pid):
        return any(p.pid == pid for p in self.players)

    def set_connected(self, pid, connected):
        self._p(pid).connected = connected
        if not connected and self.phase == "guessing":
            self._maybe_resolve()

    # ── match flow ────────────────────────────────────────────────────────
    def start(self, pid):
        if self.phase != "lobby":
            raise GameError("Game already started.")
        if pid != self.players[0].pid:
            raise GameError("Only the host can start the game.")
        if len(self.players) < 2:
            raise GameError("Need at least 2 players.")
        self._new_match()

    def play_again(self, pid):
        self._p(pid)
        if self.phase != "game_over":
            raise GameError("The game isn't over yet.")
        self.players = [p for p in self.players if p.connected]
        if len(self.players) < 2:
            raise GameError("Need at least 2 connected players.")
        self._new_match()

    def _new_match(self):
        self.rounds_played = 0
        self.giver_idx = self._pick_first()
        self.winners, self.end_reason, self.last_turn = [], None, None
        for p in self.players:
            p.score, p.tokens, p.hand = 0, cfg.EXTRA_WORD_TOKENS_PER_GAME, []
        for p in self.players:
            while len(p.hand) < cfg.CARDS_PER_PLAYER:
                p.hand.append(self._draw())
        self._begin_turn()

    def _pick_first(self):
        """First match: host opens. Rematches: the next seat after last match's opener."""
        idx = 0
        if self.first_pid is not None:
            prev = next((i for i, p in enumerate(self.players)
                         if p.pid == self.first_pid), None)
            idx = 0 if prev is None else (prev + 1) % len(self.players)
        self.first_pid = self.players[idx].pid
        return idx

    def _draw(self):
        held = {w for p in self.players for w in p.hand}
        pool = [w for w in self.vocab if w not in held]
        if not pool:
            raise GameError("Word bank is too small for this many players.")
        return self.rng.choice(pool)

    def _reset_turn(self):
        self.hidden = None
        self.hints = []            # every hint attempt this turn
        self.locked = []           # hints that were locked in (one per guess round)
        self.guess_round = 0
        self.round_attempts = 0
        self.guesses = {}          # pid -> [words] for the current guess round
        self.rounds_log = []
        self.points_this_turn = {}

    def _begin_turn(self):
        self._reset_turn()
        self.phase = "selecting"

    def select_word(self, pid, word):
        if self.phase != "selecting" or pid != self.giver.pid:
            raise GameError("You can't choose a word right now.")
        match = next((w for w in self.giver.hand if w == norm(word)), None)
        if match is None:
            raise GameError("That word isn't in your hand.")
        self.hidden = match
        self.phase = "hinting"

    # ── spell gate ────────────────────────────────────────────────────────
    def _spell_items(self, words, confirmed, allow_proper):
        """Returns suggestion items; raises in strict mode; [] when clear."""
        if not cfg.ENABLE_SPELLCHECK or cfg.SPELLCHECK_MODE == "off":
            return []
        if cfg.SPELLCHECK_MODE == "suggest" and confirmed:
            return []
        items = []
        for i, w in enumerate(words):
            r = self.spell.check(w, allow_proper=allow_proper)
            if r.status == "reject":
                raise GameError(r.message)
            if r.status == "suggest":
                items.append({"index": i, "original": w, "suggestions": r.suggestions})
        return items

    @staticmethod
    def _check_format(w):
        if not WORD_RE.match(w) or len(w) > 30:
            raise GameError("Use a single word (letters, hyphens or apostrophes).")

    # ── hint phase ────────────────────────────────────────────────────────
    def submit_hint(self, pid, word, confirmed=False):
        if self.phase != "hinting" or pid != self.giver.pid:
            raise GameError("It isn't time for a hint.")
        word = word.strip()
        self._check_format(word)
        if norm(word) == self.hidden and not cfg.ALLOW_EXACT_WORD_HINT:
            raise GameError("You can't use your hidden word as a hint.")
        if any(norm(h["word"]) == norm(word) for h in self.hints):
            raise GameError("You've already tried that hint.")
        items = self._spell_items([word], confirmed, cfg.ALLOW_PROPER_NOUN_HINTS)
        if items:
            return {"ok": False, "context": "hint", "suggest": items}
        d = self.scorer.score(self.hidden, norm(word))
        rec = self._hint_rec(word, d)
        self.hints.append(rec)
        self.round_attempts += 1
        if rec["score"] >= cfg.SIMILARITY_THRESHOLD:
            self._lock(rec)
        elif self.round_attempts >= cfg.MAX_HINT_ATTEMPTS:
            self._hint_limit()
        return {"ok": True}

    def _hint_rec(self, word, d, fallback=False):
        return {"word": word, "sem": d["sem"], "assoc": d["assoc"], "raw": d["raw"],
                "score": d["score"], "round": self.guess_round + 1,
                "locked": False, "fallback": fallback}

    def _hint_limit(self):
        near = None
        if cfg.NEAREST_NEIGHBOR_ON_LIMIT:
            used = {norm(h["word"]) for h in self.hints}
            near = self.scorer.nearest(self.hidden, used)
        if near:
            rec = self._hint_rec(near[0], near[1], fallback=True)
            self.hints.append(rec)
        else:
            rnd = [h for h in self.hints if h["round"] == self.guess_round + 1]
            rec = max(rnd, key=lambda h: h["score"])
        self._lock(rec)

    def _lock(self, rec):
        rec["locked"] = True
        self.locked.append(rec)
        self.guesses = {}
        self.phase = "guessing"
        self._maybe_resolve()

    # ── guessing phase ────────────────────────────────────────────────────
    def submit_guess(self, pid, words, use_token=False, confirmed=False):
        if self.phase != "guessing":
            raise GameError("It isn't time to guess.")
        p = self._p(pid)
        if p is self.giver:
            raise GameError("The clue-giver can't guess.")
        if pid in self.guesses:
            raise GameError("You've already guessed this round.")
        if use_token and p.tokens <= 0:
            raise GameError("You have no Extra Word Tokens left.")
        need = cfg.EXTRA_GUESSES_GRANTED if use_token else 1
        words = [w.strip() for w in words]
        if len(words) != need or not all(words):
            raise GameError(f"Enter {need} guess{'es' if need > 1 else ''}.")
        for w in words:
            self._check_format(w)
        items = self._spell_items(words, confirmed, False)
        if items:
            return {"ok": False, "context": "guess", "suggest": items}
        self.guesses[pid] = words
        if use_token:
            p.tokens -= 1
        self._maybe_resolve()
        return {"ok": True}

    def _guessers(self):
        return [p for p in self.players if p is not self.giver and p.connected]

    def _maybe_resolve(self):
        if self.phase != "guessing":
            return
        g = self._guessers()
        if g and all(p.pid in self.guesses for p in g):
            self._resolve_round()

    def _resolve_round(self):
        r = self.guess_round
        names = {p.pid: p.name for p in self.players}
        correct = [pid for pid, ws in self.guesses.items()
                   if any(norm(w) == self.hidden for w in ws)]
        self.rounds_log.append({
            "round": r + 1,
            "hint": self.locked[-1]["word"],
            "guesses": {names[pid]: ws for pid, ws in self.guesses.items()},
            "correct": [names[pid] for pid in correct]})
        if correct:
            pts = (cfg.FIRST_GUESS_CORRECT_POINTS if r == 0
                   else cfg.SUBSEQUENT_GUESS_CORRECT_POINTS)
            for pid in correct:
                self._award(pid, pts)
            return self._end_turn(True)
        table = cfg.CLUE_GIVER_FAILED_GUESS_POINTS
        self._award(self.giver.pid, table[min(r, len(table) - 1)])
        if r + 1 < cfg.MAX_GUESS_ROUNDS:
            self.guess_round += 1
            self.round_attempts = 0
            self.guesses = {}
            self.phase = "hinting"
        else:
            self._end_turn(False)

    def _award(self, pid, pts):
        self._p(pid).score += pts
        self.points_this_turn[pid] = self.points_this_turn.get(pid, 0) + pts

    # ── turn end / game end ───────────────────────────────────────────────
    def _end_turn(self, solved):
        giver = self.giver
        self.rounds_played += 1
        self.last_turn = {
            "giver": giver.name, "hidden": self.hidden, "solved": solved,
            "rounds": self.rounds_log,
            "points": {self._p(pid).name: v for pid, v in self.points_this_turn.items()}}
        giver.hand.remove(self.hidden)
        giver.hand.append(self._draw())
        reason = None
        if cfg.TARGET_WIN_SCORE is not None and any(
                p.score >= cfg.TARGET_WIN_SCORE for p in self.players):
            reason = "score"
        elif cfg.MAX_ROUNDS is not None and self.rounds_played >= cfg.MAX_ROUNDS:
            reason = "rounds"
        if reason:
            top = max(p.score for p in self.players)
            self.winners = [p.name for p in self.players if p.score == top]
            self.end_reason = reason
            self.phase = "game_over"
        else:
            self.phase = "turn_over"

    def next_turn(self, pid):
        self._p(pid)
        if self.phase != "turn_over":
            raise GameError("Nothing to continue.")
        n = len(self.players)
        for step in range(1, n + 1):
            idx = (self.giver_idx + step) % n
            if self.players[idx].connected:
                self.giver_idx = idx
                break
        self._begin_turn()

    # ── per-player view (privacy boundary) ────────────────────────────────
    def view(self, pid):
        me = self._p(pid)
        in_turn = self.phase in ("selecting", "hinting", "guessing")
        giver = self.giver if self.players and self.phase != "lobby" else None
        reveal = self.phase in ("turn_over", "game_over")
        v = {
            "phase": self.phase, "you": pid, "host": self.players[0].pid,
            "players": [{"pid": p.pid, "name": p.name, "score": p.score,
                         "tokens": p.tokens, "connected": p.connected,
                         "is_giver": p is giver and self.phase != "game_over",
                         "has_guessed": p.pid in self.guesses}
                        for p in self.players],
            "rules": {"threshold": cfg.SIMILARITY_THRESHOLD,
                      "max_hint_attempts": cfg.MAX_HINT_ATTEMPTS,
                      "max_guess_rounds": cfg.MAX_GUESS_ROUNDS,
                      "target_score": cfg.TARGET_WIN_SCORE,
                      "max_rounds": cfg.MAX_ROUNDS,
                      "show_breakdown": cfg.SHOW_SCORE_BREAKDOWN,
                      "extra_guesses": cfg.EXTRA_GUESSES_GRANTED},
            "round": self.rounds_played + (1 if in_turn else 0),
            "guess_round": self.guess_round + 1,
            "attempts_left": cfg.MAX_HINT_ATTEMPTS - self.round_attempts,
            "hints": self.hints,
            "rounds_log": self.rounds_log,    # every player's guesses, once a round resolves
            "locked_hint": self.locked[-1]["word"] if self.locked else None,
            "hand": list(me.hand),            # only ever the requester's own hand
            "hidden": None, "last_turn": self.last_turn if reveal else None,
            "winners": self.winners, "end_reason": self.end_reason,
        }
        if self.phase in ("hinting", "guessing") and me is giver:
            v["hidden"] = self.hidden
        return v
