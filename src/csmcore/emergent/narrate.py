"""Optional generative layer: words on top of the simulation, never the source of truth.

TemplateNarrator is the default and needs nothing: the game is complete and reproducible
without any model or network. LLMNarrator takes any `complete(prompt) -> str` function (a
local model, a paid API, a test stub) and uses it for prose only: news, interviews,
retrospectives, dialogue lines. If the call fails, or the text names people who are not in the
facts it was given, the template text is used instead.

`propose_action` lets a model suggest what a character does. The suggestion is a request, not a
change: it must name one of the engine's typed actions and a target the engine itself would
offer this person now, within the same budgets and cooldowns. Only then does the engine
execute it, through the same code path as any other decision.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from . import actions as A

RULES = ("Пиши по-русски. Используй только факты из списка ниже. Не придумывай событий, имён, счетов и цифр, "
         "которых нет в фактах. Если чего-то не знаешь, не пиши об этом.")


class Narrator:
    def describe(self, f) -> str:
        return f.text or f.kind

    def article(self, retro: dict, facts: list) -> str:
        body = "\n\n".join(retro["paragraphs"])
        return f"{retro['headline']}\n\n{retro.get('lead', '')}\n\n{body}".strip()

    def dialogue(self, speaker, mind, topic: str | None = None) -> str:
        k, who, v = mind.strongest()
        if v < 8:
            return f"{speaker.name}: «Всё нормально, работаем.»"
        lines = {
            "envy": f"«Все говорят только про {who}. Посмотрим, кто будет нужен команде в плей-офф.»",
            "threat": f"«{who} хороший парень, но моё место надо ещё забрать.»",
            "anger": f"«С {who} у меня есть разговор. Не для камер.»",
            "gratitude": f"«Без {who} я бы так не заиграл.»",
            "distress": "«В команде сейчас тяжело. Надо держаться вместе.»",
            "joy": "«Отличная неделя. Хочется больше таких.»",
        }
        return f"{speaker.name}: " + lines.get(k, "«Без комментариев.»")


class LLMNarrator(Narrator):
    def __init__(self, complete: Callable[[str], str], fallback: Narrator | None = None) -> None:
        self.complete = complete
        self.fallback = fallback or Narrator()
        self.failures = 0
        self.known: set[str] = set()   # every person's name the engine has seen (set by the engine)

    def _ask(self, task: str, facts: list, names: set[str]) -> str | None:
        payload = [{"id": f.id, "season": f.season, "kind": f.kind, "text": f.text,
                    "people": f.people()} for f in facts if f is not None]
        prompt = f"{RULES}\n\nЗадача: {task}\n\nФакты (JSON):\n{json.dumps(payload, ensure_ascii=False)}"
        try:
            text = self.complete(prompt)
        except Exception:
            self.failures += 1
            return None
        if not text or not grounded(text, names, self.known):
            self.failures += 1
            return None
        return text.strip()

    def describe(self, f) -> str:
        return self._ask("Одна строка новости об этом факте.", [f], set(f.people())) or self.fallback.describe(f)

    def article(self, retro: dict, facts: list) -> str:
        names = {p for f in facts if f is not None for p in f.people()} | {retro["player"]}
        return self._ask(f"Журналистский материал «{retro['headline']}» о карьере {retro['player']}.", facts, names) \
            or self.fallback.article(retro, facts)


def grounded(text: str, allowed: set[str], known: set[str]) -> bool:
    """Reject text that names a known person who is not in the facts. Nicknames in this world are
    single latin tokens, so any latin word of 3+ letters that is a nickname we know must be allowed."""
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", text):
        if w in known and w not in allowed:
            return False
    return True



def available_actions(ew, ctx, p, club) -> list[dict]:
    """What this person could really do now: the menu a model may choose from."""
    mind = ew.minds.of(p.name)
    out = []
    for act in A.ALL:
        if act.tone == A.NEG and (not ew._budget_ok(ctx, club) or mind.cooldowns.get("neg", -1) > ctx.week):
            continue
        for t, x in act.candidates(ew, ctx, p, club, mind):
            if t == p.name or mind.cooldowns.get(f"{act.name}|{t}", -1) > ctx.week:
                continue
            if act.available(ew, ctx, p, club, t, x):
                out.append({"action": act.name, "target": t, "third": x, "label": act.label})
    return out


def propose_action(ew, ctx, p, club, complete: Callable[[str], str]) -> tuple[bool, str, object]:
    """Ask a model what `p` does this week and execute it only if the engine allows it."""
    menu = available_actions(ew, ctx, p, club)
    mind = ew.minds.of(p.name)
    prompt = (f"{RULES}\nТы решаешь за {p.name}. Чувства: {json.dumps(mind.emotions, ensure_ascii=False)}. "
              f"Выбери одно действие из меню или 'rest'. Ответь JSON {{\"action\":..., \"target\":..., \"third\":...}}.\n"
              f"Меню: {json.dumps(menu, ensure_ascii=False)}")
    try:
        raw = complete(prompt)
        m = re.search(r"\{.*\}", raw, re.S)
        choice = json.loads(m.group(0)) if m else {}
    except Exception as e:   # a broken model never breaks the week
        return False, f"модель не ответила: {e.__class__.__name__}", None
    name = choice.get("action")
    if name in (None, "rest"):
        return True, "отдыхает", None
    hit = next((o for o in menu if o["action"] == name and o["target"] == choice.get("target")
                and o["third"] == choice.get("third")), None)
    if hit is None:
        return False, f"отклонено: {name} → {choice.get('target')} недоступно {p.name} сейчас", None
    act = A.BY_NAME[name]
    _, why = act.utility(ew, ctx, p, club, mind, hit["target"], hit["third"])
    f = ew._do(ctx, p, club, mind, act, hit["target"], hit["third"], why + ["решение предложено языковой моделью"],
               ew._motive(mind, hit["target"], hit["third"], act))
    return True, f.text, f
