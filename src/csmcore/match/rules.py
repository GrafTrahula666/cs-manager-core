"""Competition rules as data, with a version and the source of every number.

A tournament plays under the game's Premier defaults plus its own exceptions (Valve's Major
rulebook says exactly that), so rules are a preset plus overrides, never constants in the engine.

Every value carries a status:
    verified        read from a primary file (CS2 server config tracked by SteamDB, Valve's rules)
    engine_default  a game default that is not in those files; widely documented, not checked here
    model           a game-design choice of CS Manager, not a fact about CS2

Sources (fetched 2026-10-19, sha256 in docs/match-rules.md):
    CFG   github.com/SteamDatabase/GameTracking-CS2 game/csgo/cfg/gamemode_competitive.cfg
    TMM   the same repo, gamemode_competitive_tmm.cfg (Premier, applied after CFG)
    MSR   github.com/ValveSoftware/counter-strike_rules_and_regs major-supplemental-rulebook.md
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

# Kill award by weapon class. CS2 defines these per weapon (cash_player_killed_enemy_factor = 1
# and the default 300 are in CFG; the per-class values are engine_default).
KILL_AWARD = {"default": 300, "pistol": 300, "rifle": 300, "smg": 600, "shotgun": 900,
              "awp": 100, "knife": 1500, "grenade": 300, "zeus": 0}

VETO_MAJOR = {   # MSR "Map Pick-Ban": A/B after the higher seed chooses; side picks omitted
    "bo1": ("A:ban", "A:ban", "B:ban", "B:ban", "B:ban", "A:ban", "decider"),
    "bo3": ("A:ban", "B:ban", "A:pick", "B:pick", "B:ban", "A:ban", "decider"),
}


@dataclass(frozen=True)
class Rules:
    name: str
    as_of: str
    # format (CFG mp_maxrounds 24 = MR12; overtime from TMM / MSR)
    max_rounds: int = 24
    overtime: bool = True
    ot_max_rounds: int = 6            # MR3
    ot_limit: int = 1                 # 0 = unlimited (Major), 1 = one overtime then draw (Premier)
    # money
    start_money: int = 800
    ot_start_money: int = 12_500
    max_money: int = 16_000
    loser_bonus: int = 1_400
    loser_bonus_step: int = 500
    loser_bonus_steps: int = 4        # 1400, 1900, 2400, 2900, 3400
    half_start_loss_count: int = 1    # the pistol loser gets the second step (1900)
    win_elimination: int = 3_250
    win_time: int = 3_250
    t_win_bomb: int = 3_500
    ct_win_defuse: int = 3_500
    t_planted_lost: int = 600         # CFG cash_team_planted_bomb_but_defused
    player_planted: int = 300
    player_defused: int = 300
    killed_teammate: int = -300
    shorthanded_bonus: int = 1_000
    t_timeout_survivors_paid: bool = False   # Ts alive when time runs out get no loss bonus
    # round clock, seconds
    freeze_time: int = 20
    buy_time: int = 20
    round_time: float = 115.2         # CFG mp_roundtime 1.92 minutes
    c4_timer: int = 40
    defuse_kit: int = 5
    defuse_no_kit: int = 10
    veto: dict = field(default_factory=dict)
    status: dict = field(default_factory=dict)   # field -> verified / engine_default / model

    def kill_award(self, weapon: str) -> int:
        return KILL_AWARD.get(weapon, KILL_AWARD["default"])

    def loss_bonus(self, count: int) -> int:
        """Loss bonus for a team whose loss counter is `count` after this loss (1 = first)."""
        step = max(0, min(count - 1, self.loser_bonus_steps))
        return self.loser_bonus + self.loser_bonus_step * step

    def rounds_per_half(self, overtime: bool = False) -> int:
        return (self.ot_max_rounds if overtime else self.max_rounds) // 2


_VERIFIED = ("max_rounds", "start_money", "max_money", "loser_bonus", "loser_bonus_step", "win_elimination",
             "win_time", "t_win_bomb", "ct_win_defuse", "t_planted_lost", "player_planted", "player_defused",
             "killed_teammate", "shorthanded_bonus", "freeze_time", "buy_time", "round_time", "overtime", "ot_limit")
_ENGINE = ("ot_max_rounds", "ot_start_money", "loser_bonus_steps", "half_start_loss_count", "c4_timer",
           "defuse_kit", "defuse_no_kit", "t_timeout_survivors_paid")

PREMIER_2026 = Rules("CS2 Premier defaults", "2026-10-19",
                     status={**{k: "verified" for k in _VERIFIED}, **{k: "engine_default" for k in _ENGINE}})

# MSR: Premier defaults except cash_team_bonus_shorthanded 0 and mp_overtime_limit 0.
MAJOR_2026 = replace(PREMIER_2026, name="CS Major (Valve supplemental rulebook)", shorthanded_bonus=0, ot_limit=0,
                     veto=VETO_MAJOR, status={**PREMIER_2026.status, "veto": "verified"})

PRESETS = {"premier-2026": PREMIER_2026, "major-2026": MAJOR_2026}


def preset(name: str, **overrides) -> Rules:
    """A tournament's rules: a preset plus its own exceptions, each marked as a model choice
    unless the caller says otherwise."""
    base = PRESETS[name]
    if not overrides:
        return base
    status = {**base.status, **{k: "model" for k in overrides}}
    return replace(base, name=f"{base.name} + {', '.join(sorted(overrides))}", status=status, **overrides)
