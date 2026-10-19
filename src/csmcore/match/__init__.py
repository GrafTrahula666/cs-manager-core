"""Match rules and in-map economy, the first gate of the match-engine rework (docs/match-rules.md).

Not used by engine.py yet: the current engine keeps playing exactly as before.
"""
from .economy import CT, Entry, MapEconomy, T
from .rules import MAJOR_2026, PREMIER_2026, PRESETS, Rules, preset

__all__ = ["CT", "MAJOR_2026", "PREMIER_2026", "PRESETS", "Entry", "MapEconomy", "Rules", "T", "preset"]
