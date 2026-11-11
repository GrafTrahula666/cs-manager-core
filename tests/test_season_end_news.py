"""Season-end notifications must reach WeekNews before the old log is discarded."""

from csmcore import game as game_module, save
from csmcore.game import Game
from csmcore.season import SeasonLog


def _rollover_without_simulation(self):
    """Keep this UI regression independent of full season-world transitions."""
    old_week = self.week
    self.season += 1
    self.run.start_week = old_week
    self.run.wk = 0
    self.run.log = SeasonLog()
    return ["Сезон завершён"]


def _rng_states(game):
    return (game.rng.getstate(), game.run.rng.getstate(), game.run.meta_rng.getstate(),
            game.run.story_rng.getstate(), game.run.mgmt_rng.getstate())


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
    monkeypatch.setattr(Game, "_new_season", _rollover_without_simulation)

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


def test_year_end_news_replay_from_save_preserves_all_rng_streams(monkeypatch):
    g = Game.new(seed=67, n_clubs=24)
    g.run.wk = 51
    loaded = save.loads(save.dumps(g))
    before_rng = _rng_states(g)

    monkeypatch.setattr(
        game_module, "season_week",
        lambda run, clubs, graph, calendar, systems, plans: setattr(run, "wk", run.wk + 1),
    )
    monkeypatch.setattr(
        game_module, "season_finish",
        lambda run, clubs, systems: run.log.management.append(
            "HLTW: игрок сезона 1 — проверка доставки новости"
        ),
    )
    monkeypatch.setattr(Game, "_new_season", _rollover_without_simulation)

    assert g.advance() == loaded.advance()
    assert g.season == loaded.season == 2
    assert g.run.wk == loaded.run.wk == 0
    assert _rng_states(g) == _rng_states(loaded) == before_rng
    assert save.dumps(g) == save.dumps(loaded)
