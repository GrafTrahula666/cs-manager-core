"""Season-end notifications must reach WeekNews before the raw season log is discarded."""

import pytest

from csmcore import game as game_module, save
from csmcore.game import Game


def test_year_end_retirement_and_hltw_headlines_are_visible_once(monkeypatch):
    g = Game.new(seed=53, n_clubs=24)
    g.run.wk = 51
    own = g.club.roster[0]
    other = next(c for c in g.clubs if c is not g.club)
    rival = other.roster[0]
    own_notice = f"{own.name} ({own.age}) завершил карьеру → analyst"
    rival_notice = f"{rival.name} ({rival.age}) завершил карьеру → coach"
    hltw_notice = f"HLTW: игрок сезона 1 — {rival.name} ({other.name}), рейтинг 1.42"
    hltw_top = "HLTW топ-20 сезона 1: 1. Rival (Others)…"
    free_agents = "Без клуба из киберспорта ушли 3 свободных агента"

    def tick(run, clubs, graph, calendar, systems, plans):
        run.wk += 1
        run.log.management.append(f"{g.club_name}: обычные новости недели")

    def finish(run, clubs, systems):
        assert run.wk == 52
        run.log.management.extend([
            own_notice, rival_notice, hltw_notice, hltw_top, free_agents,
        ])

    monkeypatch.setattr(game_module, "season_week", tick)
    monkeypatch.setattr(game_module, "season_finish", finish)

    news = g.advance()

    assert news.week == 52 and news.season == 1
    assert news.lines.count(f"клуб: {g.club_name}: обычные новости недели") == 1
    assert news.lines.count(f"клуб: {own_notice}") == 1
    assert news.lines.count(f"мир: {hltw_notice}") == 1
    assert news.lines.count(f"мир: {hltw_top}") == 1
    assert news.lines.count(f"мир: {free_agents}") == 1
    assert f"клуб: {rival_notice}" not in news.lines
    assert g.season == 2 and g.run.wk == 0
    assert not g.run.log.management
    assert save.loads(save.dumps(g)).history[-1] == news

    following = g.advance()
    for line in ("клуб: " + own_notice, "мир: " + hltw_notice,
                 "мир: " + hltw_top, "мир: " + free_agents):
        assert line not in following.lines
    assert len(g.history) == 2


def test_real_year_end_is_deterministic_after_save_roundtrip():
    g = Game.new(seed=67, n_clubs=24)
    g.run.wk = 51
    loaded = save.loads(save.dumps(g))

    news_a, news_b = g.advance(), loaded.advance()
    assert news_a == news_b
    assert g.season == loaded.season == 2
    assert g.run.wk == loaded.run.wk == 0
    assert g.rng.getstate() == loaded.rng.getstate()
    for attr in ("rng", "meta_rng", "story_rng", "mgmt_rng"):
        assert getattr(g.run, attr).getstate() == getattr(loaded.run, attr).getstate()
    assert [(c.name, c.rank, c.cash, len(c.roster)) for c in g.clubs] == [
        (c.name, c.rank, c.cash, len(c.roster)) for c in loaded.clubs
    ]
    assert save.dumps(g) == save.dumps(loaded)
