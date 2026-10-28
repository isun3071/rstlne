import json
import re

import pytest
from fakes import FakeDecisions, board_reader, decide_by, router

from rstlne import settings
from rstlne.calibrate import boards, calibrate, choose_threshold
from rstlne.cli import build_players

DEV = settings.ROOT / "puzzles" / "dev.json"


def shown_share(state):
    """A fake P(solvable): the share of the board's letter squares that are showing."""
    tiles = re.search(r"^Board: (.*)$", state, re.M).group(1).split()
    letters = [t for t in tiles if t == "_" or t.isalpha()]
    return sum(t != "_" for t in letters) / len(letters)


@pytest.mark.parametrize(
    "points, threshold",
    [
        # The curve is 0 up to 0.3 and 1 from 0.5. Averaging everything above 0.3 would pass 80%; the curve doesn't.
        ([(0.1, False), (0.3, False), (0.5, True), (0.6, True), (0.7, True), (0.8, True), (0.9, True)], 0.5),
        # 0.2 (right) and 0.3 (wrong) pool into one point of the curve at 50%, so the curve reaches 80% at 0.4.
        ([(0.1, False), (0.2, True), (0.3, False), (0.4, True), (0.5, True), (0.6, True), (0.7, True), (0.8, True)], 0.4),
        ([(0.9, True), (0.95, True), (0.99, True)], None),  # fewer than 5 boards at any threshold
        ([(p / 10, False) for p in range(10)], None),  # the solver is never right
    ],
)
def test_choose_threshold(points, threshold):
    assert choose_threshold(points, target=0.8, minimum=5) == threshold


def test_boards_run_from_empty_to_full_for_each_sampled_puzzle():
    puzzles = settings.load_puzzles(DEV)
    sample = boards(puzzles, count=6, seed=42)
    assert sample == boards(puzzles, count=6, seed=42)
    by_puzzle = {}
    for board in sample:
        by_puzzle.setdefault(board.puzzle.answer, []).append(board.shown)
    assert len(by_puzzle) == 6
    for shown in by_puzzle.values():
        assert shown[0] == 0.0 and shown[-1] == 1.0 and shown == sorted(shown)
    assert not any(b.puzzle.bonus for b in sample)


def test_calibration_shares_solver_attempts_and_picks_thresholds(tmp_path):
    decisions = FakeDecisions(decide_by(shown_share))
    client = router(board_reader)  # solves only once the board is full
    result = calibrate(
        ["model/a", "model/b"], puzzles_path=DEV, count=6, seed=42, client=client, decisions=decisions,
        out_dir=tmp_path, parallel=2, write=lambda line: None,
    )
    n = result["boards"]
    assert len(client.client.calls) == n  # one solver attempt per board, shared by both models
    assert len(decisions.calls) == 2 * n
    for model in ("model/a", "model/b"):
        points = result["models"][model]["points"]
        assert len(points) == n
        expected = choose_threshold([(p["p_solvable"], p["solver_correct"]) for p in points])
        assert result["models"][model]["threshold"] == expected
        assert expected > 0.9  # the fake solver only gets full boards right, so only near-full boards qualify
    assert result["config_lines"] == [f'"model/a" = {expected}', f'"model/b" = {expected}']
    (saved,) = tmp_path.glob("calibration-*.json")
    assert json.loads(saved.read_text()) == result


def test_decision_seats_use_their_calibrated_threshold(rules, wheel_spec):
    config = settings.load_config()
    config = {**config, "decision": {**config["decision"], "thresholds": {"typesafe/jev-1.14": 0.55}}}
    seats = [("decision", "typesafe/jev-1.14"), ("decision", None), ("llm", "a/one")]
    players = build_players(seats, rules, wheel_spec, config, router([]), FakeDecisions(decide_by()), "game")
    assert players[0].threshold == 0.55
    assert players[1].model == "openai/gpt-6-luna-decisions" and players[1].threshold == config["decision"]["solve_threshold"]


def test_providers_in_config_pin_model_seats(rules, wheel_spec):
    config = {**settings.load_config(), "providers": {"deepseek/deepseek-v4.1-flash-1017": "deepseek"}}
    seats = [("llm", "deepseek/deepseek-v4.1-flash-1017"), ("llm", "openai/gpt-6-luna"), ("decision", None)]
    players = build_players(seats, rules, wheel_spec, config, router([]), FakeDecisions(decide_by()), "game")
    assert players[0].provider == "deepseek"
    assert players[1].provider is None
    assert players[2].solver.provider is None
