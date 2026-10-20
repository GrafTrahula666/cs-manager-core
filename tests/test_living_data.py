import pytest

from csmcore import livingdata
from csmcore.progression import ManagerProgression, xp_to_next


def test_data_is_consistent():
    assert livingdata.validate() == []
    t = livingdata.load("talents")
    assert len(t["nodes"]) == 60 and len(t["branches"]) == 5


def test_no_talent_changes_win_probability_directly():
    for ch in livingdata.load("talents")["channels"]:
        assert not ch.startswith("win") and "probab" not in ch


def test_points_levels_and_cap():
    m = ManagerProgression("me")
    assert m.level == 1 and m.available_points == 0
    for i in range(700):   # many distinct achievements over many seasons: levels stop at the cap
        m.grant("career_milestone", f"x{i}", season=i // 8)
    assert m.level == m.max_level == 40
    assert m.earned_points == 39 and m.available_points == 39
    assert m.grant("career_milestone", "again", season=999)["why"] == "максимальный уровень"


def test_xp_never_pays_twice_and_season_cap():
    m = ManagerProgression("me")
    a = m.grant("title_s", "s1:Major", 1)
    b = m.grant("title_s", "s1:Major", 1)
    assert a["xp"] == 400 and b["xp"] == 0 and b["why"] == "уже начислено"
    for i in range(30):   # a farm of one-off rewards stops at the season cap
        m.grant("long_task", f"t{i}", 1)
    assert m._season_xp[1] == livingdata.load("progression")["season_xp_cap"]
    assert xp_to_next(2) > xp_to_next(1)


def test_conflict_reward_limited_per_season():
    m = ManagerProgression("me")
    got = [m.grant("conflict_resolved", f"c{i}", 1)["xp"] for i in range(6)]
    assert got.count(40) == 3 and got.count(0) == 3


def test_unlock_needs_points_and_prerequisites():
    m = ManagerProgression("me")
    with pytest.raises(ValueError):
        m.unlock("str_dossier")   # no points yet
    for i in range(10):
        m.grant("career_milestone", f"x{i}", season=i)
    assert m.available_points > 3
    with pytest.raises(ValueError):
        m.unlock("str_styles")    # needs the dossier first
    m.unlock("str_dossier")
    m.unlock("str_styles")
    with pytest.raises(ValueError):
        m.unlock("str_styles")    # not twice
    assert m.spent_points == 2 and m.channel("prep.opponent_report") == 0.10


def test_channel_total_is_clamped_by_cap():
    cap = livingdata.load("talents")["channels"]["neg.contract"]["cap"]
    allm = {n["id"] for n in livingdata.load("talents")["nodes"]}
    assert livingdata.channel_total(allm, "neg.contract") <= cap
    assert livingdata.channel_total(allm, "prep.opponent_report") <= livingdata.load("talents")["channels"]["prep.opponent_report"]["cap"]


def test_one_career_cannot_take_every_talent():
    assert 39 < len(livingdata.load("talents")["nodes"])


def test_ladder_reaches_mid_levels_in_five_or_six_seasons_with_good_play():
    """A strong season: owner goals, one A title, exceeded rank. Hypothesis from docs/living-club.md."""
    m = ManagerProgression("me")
    for s in range(1, 7):
        m.grant("owner_goal", f"{s}:rank", s); m.grant("owner_goal", f"{s}:cash", s)
        m.grant("title_a", f"{s}:cup", s); m.grant("exceeded_rank", str(s), s)
        m.grant("infra_project", f"p{s}", s); m.grant("long_task", f"t{s}", s)
    assert 10 <= m.level <= 22
