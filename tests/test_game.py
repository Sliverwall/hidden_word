import json

import pytest

import config
from conftest import VOCAB, guess_all, lock_hint
from embeddings import calibrate
from game_engine import Game, GameError
from word_bank import WordBankError, load_words


# ── scoring escalation (config-driven) ────────────────────────────────────
def test_clue_giver_points_escalate(make_game):
    g = make_game()
    giver = g.giver
    for expected in (1, 3, 7, 13):
        lock_hint(g, "close" if g.guess_round == 0 else f"close{'2' if g.guess_round == 1 else ''}"
                  if g.guess_round < 2 else "close")
        guess_all(g, "wrong")
        assert giver.score == expected
        if g.phase == "hinting":
            g.scorer.table.update({f"h{g.guess_round}": 0.99})
            g.hints.clear()
    assert g.phase == "turn_over" and g.last_turn["solved"] is False
    assert g.last_turn["hidden"] == "apple"


def test_points_table_is_read_from_config(make_game, monkeypatch):
    monkeypatch.setattr(config, "CLUE_GIVER_FAILED_GUESS_POINTS", [5, 5])
    monkeypatch.setattr(config, "MAX_GUESS_ROUNDS", 2)
    g = make_game()
    lock_hint(g); guess_all(g, "x1")
    g.hints.clear(); lock_hint(g); guess_all(g, "x2")
    assert g.giver.score == 10 and g.phase == "turn_over"


def test_first_vs_subsequent_correct_points(make_game):
    g = make_game()
    lock_hint(g); guess_all(g, "apple")
    assert [p.score for p in g.players] == [0, 2, 2]

    g = make_game()
    lock_hint(g); guess_all(g, "nope")
    g.hints.clear(); lock_hint(g)
    guess_all(g, "apple")
    assert g.players[0].score == 1                     # keeps earlier failed-round points
    assert [p.score for p in g.players[1:]] == [1, 1]


# ── game end ──────────────────────────────────────────────────────────────
def test_win_score_ends_game(make_game, monkeypatch):
    monkeypatch.setattr(config, "TARGET_WIN_SCORE", 2)
    g = make_game()
    lock_hint(g); guess_all(g, "apple")
    assert g.phase == "game_over" and g.end_reason == "score"


def test_max_rounds_and_ties(make_game, monkeypatch):
    monkeypatch.setattr(config, "MAX_ROUNDS", 1)
    g = make_game()
    lock_hint(g); guess_all(g, "apple")
    assert g.phase == "game_over" and g.end_reason == "rounds"
    assert sorted(g.winners) == ["P1", "P2"]           # tie preserved


def test_no_end_conditions_rotates_giver(make_game):
    g = make_game()
    lock_hint(g); guess_all(g, "apple")
    assert g.phase == "turn_over"
    first = g.giver.pid
    g.next_turn(first)
    assert g.giver.pid == g.players[1].pid and g.phase == "selecting"


def test_play_again_resets_scores_and_tokens(make_game, monkeypatch):
    monkeypatch.setattr(config, "MAX_ROUNDS", 1)
    g = make_game()
    lock_hint(g)
    g.submit_guess(g.players[1].pid, ["a", "b"], use_token=True)
    g.submit_guess(g.players[2].pid, ["apple"])
    assert g.phase == "game_over" and g.players[1].tokens == 0
    g.play_again(g.players[0].pid)
    assert all(p.score == 0 and p.tokens == 1 for p in g.players)
    assert g.phase == "selecting"


# ── extra word tokens ─────────────────────────────────────────────────────
def test_token_consumed_and_limited(make_game):
    g = make_game()
    lock_hint(g)
    p = g.players[1]
    with pytest.raises(GameError):
        g.submit_guess(p.pid, ["one"], use_token=True)  # needs 2 guesses
    assert p.tokens == 1
    g.submit_guess(p.pid, ["one", "two"], use_token=True)
    assert p.tokens == 0
    g.submit_guess(g.players[2].pid, ["zzz"])
    g.hints.clear(); lock_hint(g)
    with pytest.raises(GameError):
        g.submit_guess(p.pid, ["a", "b"], use_token=True)


def test_two_correct_guesses_award_once(make_game):
    g = make_game()
    lock_hint(g)
    g.submit_guess(g.players[1].pid, ["apple", "apple"], use_token=True)
    g.submit_guess(g.players[2].pid, ["no"])
    assert g.players[1].score == 2


def test_token_not_spent_while_suggestion_pending(make_game, monkeypatch):
    monkeypatch.setattr(config, "SPELLCHECK_MODE", "suggest")
    g = make_game()
    lock_hint(g)
    p = g.players[1]
    r = g.submit_guess(p.pid, ["aple", "hot"], use_token=True)
    assert r["ok"] is False and "apple" in r["suggest"][0]["suggestions"]
    assert p.tokens == 1 and p.pid not in g.guesses
    r = g.submit_guess(p.pid, ["aple", "hot"], use_token=True, confirmed=True)
    assert r["ok"] and p.tokens == 0


# ── spell check ───────────────────────────────────────────────────────────
def test_suggest_mode_for_hints(make_game, monkeypatch):
    monkeypatch.setattr(config, "SPELLCHECK_MODE", "suggest")
    g = make_game()
    r = g.submit_hint(g.giver.pid, "aple")
    assert not r["ok"] and r["suggest"][0]["original"] == "aple" and not g.hints
    assert g.submit_hint(g.giver.pid, "aple", confirmed=True)["ok"]


def test_strict_mode_rejects(make_game, monkeypatch):
    monkeypatch.setattr(config, "SPELLCHECK_MODE", "strict")
    g = make_game()
    with pytest.raises(GameError):
        g.submit_hint(g.giver.pid, "qzxvbn")
    with pytest.raises(GameError):                     # confirming doesn't bypass strict
        g.submit_hint(g.giver.pid, "qzxvbn", confirmed=True)


def test_proper_noun_hint_allowed_and_case_preserved(make_game, monkeypatch):
    monkeypatch.setattr(config, "SPELLCHECK_MODE", "strict")
    g = make_game()
    assert g.submit_hint(g.giver.pid, "Zorblax")["ok"]
    assert g.hints[0]["word"] == "Zorblax"


def test_proper_noun_blocked_when_disabled(make_game, monkeypatch):
    monkeypatch.setattr(config, "SPELLCHECK_MODE", "strict")
    monkeypatch.setattr(config, "ALLOW_PROPER_NOUN_HINTS", False)
    g = make_game()
    with pytest.raises(GameError):
        g.submit_hint(g.giver.pid, "Zorblax")


# ── hints ─────────────────────────────────────────────────────────────────
def test_hint_limit_uses_nearest_neighbor(make_game, monkeypatch):
    monkeypatch.setattr(config, "MAX_HINT_ATTEMPTS", 3)
    g = make_game()
    for w in ("far", "far1", "far2"):
        g.submit_hint(g.giver.pid, w)
    assert g.phase == "guessing"
    assert g.hints[-1]["fallback"] and g.locked[-1]["word"] == "wd059"


def test_hint_limit_without_nearest_locks_best(make_game, monkeypatch):
    monkeypatch.setattr(config, "MAX_HINT_ATTEMPTS", 2)
    monkeypatch.setattr(config, "NEAREST_NEIGHBOR_ON_LIMIT", False)
    g = make_game()
    g.scorer.table["mid"] = 0.6
    g.submit_hint(g.giver.pid, "far"); g.submit_hint(g.giver.pid, "mid")
    assert g.locked[-1]["word"] == "mid"


def test_exact_word_hint_toggle(make_game, monkeypatch):
    g = make_game()
    g.submit_hint(g.giver.pid, "apple")
    assert g.phase == "guessing"
    monkeypatch.setattr(config, "ALLOW_EXACT_WORD_HINT", False)
    g = make_game()
    with pytest.raises(GameError):
        g.submit_hint(g.giver.pid, "Apple")


# ── privacy ───────────────────────────────────────────────────────────────
def test_private_hand_and_hidden_word_isolation(make_game):
    g = make_game()
    giver, other = g.giver, g.players[1]
    blob = json.dumps(g.view(other.pid))
    assert not any(w in blob for w in giver.hand)
    assert g.view(other.pid)["hidden"] is None
    assert g.view(giver.pid)["hidden"] == "apple"
    assert g.view(other.pid)["hand"] == other.hand
    lock_hint(g)
    assert "apple" not in json.dumps(g.view(other.pid))


def test_used_word_replaced_in_hand(make_game):
    g = make_game()
    giver = g.giver
    lock_hint(g); guess_all(g, "apple")
    assert "apple" not in giver.hand and len(giver.hand) == 5


# ── word bank & calibration ───────────────────────────────────────────────
def test_word_bank_errors(tmp_path):
    with pytest.raises(WordBankError):
        load_words(str(tmp_path / "missing.csv"))
    empty = tmp_path / "e.csv"; empty.write_text("")
    with pytest.raises(WordBankError):
        load_words(str(empty))
    ok = tmp_path / "w.csv"; ok.write_text("word\nApple\nbanana\n")
    assert load_words(str(ok)) == ["apple", "banana"]


def test_calibration_monotonic_and_hits_threshold():
    xs = [i / 100 for i in range(101)]
    ys = [calibrate(x) for x in xs]
    assert all(a <= b for a, b in zip(ys, ys[1:]))
    assert calibrate(0.65) >= 0.95 and calibrate(0.1) < 0.3


# ── shared guesses & rematch rotation ─────────────────────────────────────
def test_all_players_see_every_guess_after_round(make_game):
    g = make_game()
    lock_hint(g)
    g.submit_guess(g.players[1].pid, ["alpha"])
    assert g.view(g.players[2].pid)["rounds_log"] == []      # hidden until round resolves
    g.submit_guess(g.players[2].pid, ["beta"])
    for p in g.players:
        log = g.view(p.pid)["rounds_log"]
        assert log[0]["guesses"] == {"P1": ["alpha"], "P2": ["beta"]}
        assert log[0]["hint"] == "close"


def test_first_giver_rotates_between_games(make_game, monkeypatch):
    monkeypatch.setattr(config, "MAX_ROUNDS", 1)
    g = make_game()
    openers = [g.giver.name]
    for _ in range(3):
        lock_hint(g); guess_all(g, "apple")
        assert g.phase == "game_over"
        g.play_again(g.players[0].pid)
        g.giver.hand[0] = "apple"; g.select_word(g.giver.pid, "apple")
        openers.append(g.giver.name)
    assert openers == ["P0", "P1", "P2", "P0"]


def test_view_never_leaks_hand_to_other_players_after_reconnect(make_game):
    g = make_game()
    other = g.players[1]
    g.set_connected(other.pid, False); g.set_connected(other.pid, True)
    v = g.view(other.pid)
    assert v["hand"] == other.hand and v["hidden"] is None
