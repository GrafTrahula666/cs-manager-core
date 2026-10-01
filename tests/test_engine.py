from csmcore.engine import duel_win_prob, play_map
from csmcore.player import STATS, Player


def make_team(prefix: str, level: float) -> list[Player]:
    return [Player(f"{prefix}{i}", {s: level for s in STATS}) for i in range(5)]


def test_equal_players_are_coinflip():
    a, b = make_team("a", 70)[0], make_team("b", 70)[0]
    assert abs(duel_win_prob(a, b) - 0.5) < 1e-9


def test_same_seed_same_result():
    a, b = make_team("a", 70), make_team("b", 60)
    assert play_map(a, b, seed=7).score == play_map(a, b, seed=7).score


def test_stronger_team_wins_more_often():
    a, b = make_team("a", 75), make_team("b", 60)
    wins = sum(play_map(a, b, seed=s).score[0] > play_map(a, b, seed=s).score[1] for s in range(200))
    assert wins > 150
