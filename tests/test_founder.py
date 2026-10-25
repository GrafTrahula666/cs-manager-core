"""Founder gameplay: onboarding, owned club, governance and regional promotion.

Legacy manager-based simulations are intentionally still supported for old saves and AI.
"""
import pytest

from csmcore import circuit, save
from csmcore.game import Game
from csmcore.founder import candidates, sign


PROFILE = {
    "mode": "founder",
    "name": "Алексей Смирнов",
    "age": 30,
    "country": "RU",
    "background": "entrepreneur",
    "specialization": "manager",
    "traits": ["patient", "frugal"],
    "face": {},
    "club_name": "Northern Wolves",
    "club_region": "CIS",
}


def new(seed=7):
    return Game.new(seed=seed, n_clubs=120, profile=PROFILE)


def test_founder_in_third_division_with_own_club_and_money():
    g = new()
    assert g.founder_mode
    assert g.club.name == PROFILE["club_name"]
    assert g.club.region == "CIS"
    assert g.club.division == 3
    assert g.club.tier == "tier3"
    assert g.club.cash == 120_000
    assert len(g.club.roster) == 3
    assert len(g.clubs) == 120
    assert g.desk.owner.founder_mode
    assert g.desk.owner.subsidy_year == 0
    assert g.club.ledger[0].item == "founder_capital"
    assert len(candidates(g)) == 8
    assert len({p.name for c in g.clubs for p in c.roster}) == len(
        [p for c in g.clubs for p in c.roster]
    )


def test_two_real_signings_before_week_one_and_save_roundtrip():
    g = new()
    with pytest.raises(ValueError, match="пять человек"):
        g.advance()
    available = candidates(g)
    assert len(available) >= 2
    sign(g, available[0]["name"])
    assert len(g.club.roster) == 4
    with pytest.raises(ValueError, match="пять человек"):
        g.advance()
    with pytest.raises(ValueError):
        sign(g, available[0]["name"])
    sign(g, available[1]["name"])
    assert len(g.club.roster) == 5
    assert len(g.club.contracts) == 5
    before = [(p.name, g.club.contracts[p.name].contract_id) for p in g.club.roster]
    restored = save.loads(save.dumps(g))
    assert restored.founder_mode
    assert [(p.name, restored.club.contracts[p.name].contract_id) for p in restored.club.roster] == before
    assert restored.club.cash == g.club.cash
    assert restored.week == 0
    assert restored.advance().week == 1
    assert g.advance().lines == restored.history[-1].lines


def test_founder_cannot_be_fired_or_switch_clubs():
    g = new()
    b = g.desk.owner
    b.confidence = 0
    b.patience = 50
    b.monthly_review(g.club, 4)
    assert not b.fired
    assert not g.sacked
    assert not g.job_offers()
    with pytest.raises(ValueError, match="собственным клубом"):
        g.take_job(g.clubs[0].name)
    # Other clubs retain the pre-existing manager/firing simulation.
    other = next(c for c in g.clubs if c is not g.club)
    ai = g.sysm.owners[other.name]
    assert not ai.founder_mode
    ai.confidence = 0
    ai.monthly_review(other, 4)
    assert ai.fired


def test_regional_top_two_and_international_bo3_winners():
    g = new()
    qualifying = circuit.regional_candidates(g.clubs)
    assert qualifying
    assert all(c.division == 3 for c in qualifying)
    assert all(sum(q.region == c.region for q in qualifying) <= 2 for c in qualifying)
    winners, news = g._regional_playoffs()
    assert 0 < len(winners) <= 4
    assert set(winners).issubset({c.name for c in qualifying})
    assert any("Квалификация" in t for t in news)
    # Promotion is decided by the winners, not simply the 4 highest globally.
    circuit.season_end(g.clubs, winners)
    assert all(next(c for c in g.clubs if c.name == name).division == 2 for name in winners)


def test_legacy_entrypoint_is_not_retroactively_rewritten():
    g = Game.new(seed=7, n_clubs=24)
    assert not g.founder_mode
    assert len(g.club.roster) == 5
    assert not g.desk.owner.founder_mode


def test_founder_validation_does_not_mutate_an_existing_club():
    with pytest.raises(ValueError, match="название клуба"):
        Game.new(seed=7, n_clubs=120, profile={**PROFILE, "club_name": "X"})
    with pytest.raises(ValueError, match="регион"):
        Game.new(seed=7, n_clubs=120, profile={**PROFILE, "club_region": "Moon"})
