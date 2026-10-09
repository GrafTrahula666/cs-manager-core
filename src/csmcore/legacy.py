"""Careers end, legends stay (Crusader Kings dynasties, FM regens, Dwarf Fortress legends).

At season end players decide whether to retire: age, declining mechanics, burnout, money
already earned and titles all count. Retired players move into second careers that keep them
in the world: coach (raises a club's coach quality), analyst, caster or agent. New talents
are born every season so the world never runs dry; some of them grew up idolising a legend
and inherit a trait from him.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .economy import Club
from .generate import Nicknames, make_player
from .player import Player
from .development import roll_potential


@dataclass
class Retired:
    player: Player
    week: int
    second_career: str
    club: str | None = None


@dataclass
class Legacy:
    retired: list[Retired] = field(default_factory=list)
    born: list[Player] = field(default_factory=list)

    def retirement_chance(self, p: Player) -> float:
        if p.age < 27:
            return 0.0
        x = (p.age - 27) * 0.08
        x += max(0.0, 70 - p.stats.get("reaction", 50)) * 0.01
        x += p.s("burnout") / 200 + max(0.0, 50 - p.s("motivation")) / 200
        x += min(0.15, p.earnings / 3_000_000)
        x -= p.p("ambition") / 400
        return max(0.0, min(0.95, x))

    def second_career(self, p: Player) -> str:
        options = {
            "coach": p.stat("leadership") + p.stat("analytical"),
            "analyst": p.stat("analytical") * 1.6,
            "caster": p.p("media") * 1.8 + p.stat("communication") * 0.2,
            "agent": p.p("money_focus") * 1.7,
        }
        return max(options, key=options.get)

    def season_end(self, clubs: list[Club], week: int, rng: random.Random) -> list[str]:
        notes = []
        for club in clubs:
            for p in list(club.roster):
                if rng.random() >= self.retirement_chance(p):
                    continue
                club.roster.remove(p)
                club.contracts.pop(p.name, None)
                career = self.second_career(p)
                hired = None
                if career == "coach":
                    hired = max(clubs, key=lambda c: (c is club) * 1000 + c.brand)
                    hired.coach_quality = min(100.0, max(hired.coach_quality, (p.stat("leadership") + p.stat("analytical")) / 2))
                p.history.append(f"week {week}: завершил карьеру, стал {career}")
                self.retired.append(Retired(p, week, career, hired.name if hired else None))
                notes.append(f"{p.name} ({p.age}) завершил карьеру → {career}" + (f" в {hired.name}" if hired else ""))
        return notes

    def new_talents(self, n: int, rng: random.Random, season: int, taken=()) -> list[Player]:
        roles = ["entry", "awp", "rifler", "support", "lurker", "igl"]
        out = []
        legends = [r.player for r in self.retired if r.player.fame > 20 or len(r.player.history) > 6]
        for i in range(n):
            age = rng.randint(16, 18)
            nick = Nicknames(rng, reserved=set(taken) | {q.name for q in self.born} | {r.player.name for r in self.retired})
            p = make_player(nick(), rng.uniform(45, 60), rng, rng.choice(roles), age=age)
            p.potential = roll_potential(p.overall(), age, rng)
            if legends and rng.random() < 0.15:
                idol = rng.choice(legends)
                inherited = [t for t in idol.traits if t not in p.traits][:1]
                p.traits += inherited
                p.history.append(f"вырос на играх легенды {idol.name}" + (f", перенял {inherited[0]}" if inherited else ""))
            self.born.append(p)
            out.append(p)
        return out
