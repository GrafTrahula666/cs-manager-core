"""Emergent World Engine: facts, knowledge, minds, typed actions and the causal graph.

See docs/emergent-world.md. Entry point: EmergentWorld (sim.py), driven once a week from
season.season_week and told about matches by season.run_tournament.
"""
from .facts import Fact, FactLog
from .minds import Mind, Minds
from .sim import EmergentWorld, Situation, WeekCtx

__all__ = ["EmergentWorld", "Fact", "FactLog", "Mind", "Minds", "Situation", "WeekCtx"]
