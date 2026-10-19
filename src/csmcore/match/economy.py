"""Money inside a map: every player's cash, the teams' loss counters and a ledger of every change.

Gate 1 of the match-engine plan from the CS2 Combat Atlas: the money is exact and explains
itself; who buys what and who wins rounds is decided elsewhere (today engine.py does not use this
module yet). Invariants, checked by `check()` and the tests:
    0 <= cash <= rules.max_money for every player at every moment;
    cash = opening cash of the half + sum of that player's ledger entries since then;
    a purchase never makes cash negative (it is refused instead);
    a kill pays the killer only; the victim's cash does not change.

Two behaviours are game defaults that the server config does not show (status engine_default in
rules.py): the loss counter steps down by one after a win instead of resetting, and Ts who are
alive when the round time runs out get no loss bonus.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .rules import Rules

T, CT = "T", "CT"
REASONS = {"elimination", "bomb", "defuse", "time"}


@dataclass
class Entry:
    round: int
    player: str
    kind: str          # start, buy, kill, teamkill, plant, defuse, win, loss, planted_lost
    amount: int        # what was asked for (negative for a purchase or a penalty)
    applied: int       # what actually changed after the 0 floor and the max_money cap
    after: int
    note: str = ""


@dataclass
class MapEconomy:
    rules: Rules
    sides: dict[str, str]                       # player -> T or CT for the current half
    cash: dict[str, int] = field(default_factory=dict)
    losses: dict[str, int] = field(default_factory=dict)   # side -> loss counter
    ledger: list[Entry] = field(default_factory=list)
    round: int = 0
    _opening: dict[str, int] = field(default_factory=dict)
    _since: int = 0

    def __post_init__(self) -> None:
        if not self.cash:
            self.start_half(overtime=False)

    # --- halves ---
    def start_half(self, overtime: bool = False, swap: bool = False) -> None:
        """New half: sides swap if asked, cash resets to the start (or overtime) money."""
        if swap:
            self.sides = {p: CT if s == T else T for p, s in self.sides.items()}
        money = self.rules.ot_start_money if overtime else self.rules.start_money
        self.losses = {T: self.rules.half_start_loss_count, CT: self.rules.half_start_loss_count}
        self._since = len(self.ledger)
        for p in sorted(self.sides):
            self.cash[p] = 0
            self._change(p, "start", money, "овертайм" if overtime else "начало половины")
        self._opening = {p: 0 for p in self.sides}

    @classmethod
    def from_state(cls, rules: Rules, sides: dict[str, str], cash: dict[str, int], losses: dict[str, int]) -> MapEconomy:
        """A map in progress (a saved game, a test case): the given cash opens the ledger."""
        eco = cls(rules, dict(sides))
        eco.ledger.clear()
        eco.losses = dict(losses)
        for p in sorted(sides):
            eco.cash[p] = 0
            eco._change(p, "start", cash[p], "состояние")
        return eco

    def team(self, side: str) -> list[str]:
        return sorted(p for p, s in self.sides.items() if s == side)

    # --- inside a round ---
    def buy(self, player: str, cost: int, item: str = "", for_player: str | None = None) -> bool:
        """The payer buys (for himself or as a drop for a teammate). Refused if he cannot pay."""
        if cost < 0:
            raise ValueError("cost must be >= 0")
        if self.cash[player] < cost:
            return False
        note = item + (f" для {for_player}" if for_player and for_player != player else "")
        self._change(player, "buy", -cost, note)
        return True

    def kill(self, killer: str, victim: str, weapon: str = "default") -> None:
        if self.sides[killer] == self.sides[victim]:
            self._change(killer, "teamkill", self.rules.killed_teammate, victim)
        else:
            self._change(killer, "kill", self.rules.kill_award(weapon), f"{victim} ({weapon})")

    def plant(self, player: str) -> None:
        if self.sides[player] != T:
            raise ValueError("only a T plants")
        self._change(player, "plant", self.rules.player_planted)

    def defuse(self, player: str) -> None:
        if self.sides[player] != CT:
            raise ValueError("only a CT defuses")
        self._change(player, "defuse", self.rules.player_defused)

    def end_round(self, winner: str, reason: str, planted: bool = False, alive: set[str] | None = None) -> None:
        """Team awards. `alive`: players alive at the end (only matters when time runs out)."""
        if winner not in (T, CT) or reason not in REASONS:
            raise ValueError(f"bad round end: {winner} {reason}")
        if (reason == "bomb" and winner != T) or (reason in ("defuse", "time") and winner != CT):
            raise ValueError(f"{winner} cannot win by {reason}")
        if planted and (reason == "time" or (winner == CT and reason != "defuse")):
            raise ValueError("after a plant the CT win only by defusing; the clock stops mattering")
        if not planted and reason in ("bomb", "defuse"):
            raise ValueError(f"{reason} without a plant")
        r = self.rules
        win = {"elimination": r.win_elimination, "time": r.win_time, "bomb": r.t_win_bomb,
               "defuse": r.ct_win_defuse}[reason]
        loser = CT if winner == T else T
        self.losses[loser] = min(self.losses[loser] + 1, r.loser_bonus_steps + 1)
        bonus = r.loss_bonus(self.losses[loser])
        for p in self.team(winner):
            self._change(p, "win", win, reason)
        for p in self.team(loser):
            if loser == T and reason == "time" and not r.t_timeout_survivors_paid and p in (alive or set()):
                self._change(p, "loss", 0, "дожил до конца времени: без бонуса")
                continue
            self._change(p, "loss", bonus, f"серия {self.losses[loser]}")
            if loser == T and planted:
                self._change(p, "planted_lost", r.t_planted_lost)
        self.losses[winner] = max(0, self.losses[winner] - 1)
        self.round += 1

    # --- bookkeeping ---
    def _change(self, player: str, kind: str, amount: int, note: str = "") -> Entry:
        before = self.cash[player]
        after = max(0, min(self.rules.max_money, before + amount))
        e = Entry(self.round, player, kind, amount, after - before, after, note)
        self.cash[player] = after
        self.ledger.append(e)
        return e

    def check(self) -> None:
        """Raise if an invariant is broken."""
        for p, c in self.cash.items():
            assert 0 <= c <= self.rules.max_money, f"{p}: cash {c}"
            assert self._opening.get(p, 0) + sum(e.applied for e in self.ledger[self._since:] if e.player == p) == c, p
        for e in self.ledger:
            assert e.kind != "buy" or e.applied == e.amount, f"{e.player} bought on credit"

    def explain(self, player: str, last: int = 10) -> list[str]:
        """The player's money story, for the UI and for debugging."""
        out = []
        for e in [e for e in self.ledger if e.player == player][-last:]:
            capped = "" if e.applied == e.amount else f" (зачтено {e.applied:+d})"
            out.append(f"R{e.round + 1} {e.kind} {e.amount:+d}{capped} → {e.after} {e.note}".rstrip())
        return out
