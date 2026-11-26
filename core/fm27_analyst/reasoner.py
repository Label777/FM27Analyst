"""Tactical Reasoner — советы и ответы на вопросы через LLM.

LLM получает только проверенные факты (с id), сработавшие правила и
допустимые настройки FM27. Ответ — строгий JSON. После ответа идёт
проверка: ссылки только на существующие факты, игроки — только из
состава, настройки — только из справочника или из данных сейва.
Всё, что не прошло проверку, выбрасывается. Нет ключа или ошибка —
используются советы по правилам (advisor.py).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from . import advisor
from . import reference as ref
from .models import Fact, Recommendation, RecommendationAction, Signal, Snapshot
from .timeline import Timeline

log = logging.getLogger(__name__)

MODEL_FAST = os.environ.get("FM27_MODEL_FAST", "claude-haiku-5-5")
MODEL_DEEP = os.environ.get("FM27_MODEL_DEEP", "claude-sonnet-5-5")

SYSTEM_PROMPT = """Ты — ассистент главного тренера в Football Manager 27. Говоришь по-русски, коротко и по делу, как профессиональный тренерский штаб.

Жёсткие правила:
1. Используй ТОЛЬКО факты из списка FACTS. Каждое утверждение о матче подкрепляй id факта. Не выдумывай статистику.
2. Предлагай ТОЛЬКО настройки из ALLOWED: тактические правки по их id, роли — только из списка ролей, игроков — только по именам из состава.
3. Не предлагай изменения ради изменений. Если тактика работает (есть сигнал tactic_working) — так и скажи, менять нечего.
4. Всегда указывай риски. Отделяй факты от предположений.
5. Если данных не хватает — перечисли, какой экран нужно сфотографировать, в missing_data.
6. Не больше 3 действий. Самое полезное — первым."""

REC_SCHEMA = """Ответь одним JSON-объектом без пояснений:
{"recommendations": [{
  "problem": "строка",
  "evidence_fact_ids": ["id факта", ...],
  "actions": [{"text": "что сделать и почему", "kind": "tactical_tweak|role|instruction|substitution|shout|other", "setting": "id правки | роль | Игрок->Запасной | null"}],
  "expected_effect": "строка",
  "risks": "строка",
  "confidence": "low|medium|high",
  "missing_data": ["строка", ...]
}]}
Если менять ничего не нужно — {"recommendations": []}."""

ANSWER_SCHEMA = """Ответь одним JSON-объектом без пояснений:
{"short": "ответ для озвучки, не больше 25 слов",
 "detail": "подробное объяснение, 2–5 предложений",
 "evidence_fact_ids": ["id факта", ...],
 "missing_data": ["какой экран нужен", ...]}"""


class LLMProvider(Protocol):
    def complete(self, system: str, user: str, model: str, max_tokens: int) -> str: ...


class AnthropicProvider:
    def __init__(self, api_key: str | None = None) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, system: str, user: str, model: str, max_tokens: int) -> str:
        msg = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def default_provider() -> LLMProvider | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        return AnthropicProvider()
    except Exception as e:  # pragma: no cover
        log.warning("LLM недоступна: %s", e)
        return None


@dataclass
class Answer:
    short: str
    detail: str
    evidence_fact_ids: list[str]
    missing_data: list[str]
    generated_by: str = "rules"


def allowed_settings(snap: Snapshot) -> dict:
    roles = sorted({p.role for p in snap.us.players + snap.us.bench if p.role})
    return {
        "tactical_tweaks": [
            {"id": t["id"], "name": t["name_ru"], "effect": t["effect"], "risk": t["risk"]}
            for t in ref.load()["tactical_tweaks"]
        ],
        "roles_seen_in_save": roles,
        "players_on_pitch": [p.name for p in snap.us.players if p.on_pitch],
        "bench": [p.name for p in snap.us.bench],
    }


def _context_block(tl: Timeline, facts: list[Fact], signals: list[Signal], memory: list[str]) -> str:
    snap = tl.latest
    assert snap is not None
    lines = ["FACTS:"]
    lines += [f"- [{f.id}] {f.text}" for f in facts]
    lines.append("\nSIGNALS (сработавшие правила):")
    lines += [f"- {s.rule_id} ({s.severity.value}): {s.title}" for s in signals] or ["- нет"]
    lines.append("\nALLOWED:")
    lines.append(json.dumps(allowed_settings(snap), ensure_ascii=False))
    if memory:
        lines.append("\nПАМЯТЬ СЕЙВА (что раньше советовали и чем кончилось):")
        lines += [f"- {m}" for m in memory]
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("в ответе нет JSON")
    return json.loads(m.group(0))


def validate_action(a: RecommendationAction, snap: Snapshot) -> bool:
    allowed = allowed_settings(snap)
    if a.kind == "tactical_tweak":
        return a.setting in ref.tweak_ids()
    if a.kind == "role":
        return a.setting in allowed["roles_seen_in_save"]
    if a.kind == "substitution":
        if not a.setting or "->" not in a.setting:
            return False
        out, inn = (x.strip() for x in a.setting.split("->", 1))
        return out in allowed["players_on_pitch"] and inn in allowed["bench"]
    return True


def validate_recommendation(raw: dict, facts: list[Fact], snap: Snapshot, mode: str) -> Recommendation | None:
    known = {f.id for f in facts}
    try:
        actions = [RecommendationAction(**a) for a in raw.get("actions", [])]
    except ValidationError:
        return None
    actions = [a for a in actions if validate_action(a, snap)][:3]
    evidence = [i for i in raw.get("evidence_fact_ids", []) if i in known]
    if not actions or not evidence:
        return None
    try:
        return Recommendation(
            minute=snap.minute,
            mode=mode,
            problem=raw["problem"],
            evidence_fact_ids=evidence,
            actions=actions,
            expected_effect=raw.get("expected_effect", ""),
            risks=raw.get("risks") or "Не указаны — уточните",
            confidence=raw.get("confidence", "low"),
            missing_data=raw.get("missing_data", []),
            generated_by="llm",
        )
    except (ValidationError, KeyError):
        return None


class Reasoner:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider

    @property
    def has_llm(self) -> bool:
        return self.provider is not None

    def recommend(
        self,
        tl: Timeline,
        facts: list[Fact],
        signals: list[Signal],
        mode: str = "live",
        memory: list[str] | None = None,
    ) -> list[Recommendation]:
        fallback = advisor.build(tl, signals, mode)
        if not self.provider or tl.latest is None:
            return fallback
        snap = tl.latest
        user = _context_block(tl, facts, signals, memory or []) + "\n\n" + REC_SCHEMA
        model = MODEL_DEEP if mode == "head_coach" else MODEL_FAST
        try:
            data = _extract_json(self.provider.complete(SYSTEM_PROMPT, user, model, 1500))
        except Exception as e:
            log.warning("LLM-совет не получен, советы по правилам: %s", e)
            return fallback
        recs = [r for raw in data.get("recommendations", []) if (r := validate_recommendation(raw, facts, snap, mode))]
        if data.get("recommendations") and not recs:
            log.warning("Все LLM-советы отброшены проверкой — советы по правилам")
            return fallback
        return recs

    def answer(
        self,
        question: str,
        tl: Timeline,
        facts: list[Fact],
        signals: list[Signal],
        memory: list[str] | None = None,
    ) -> Answer:
        if tl.latest is None:
            return Answer(
                short="Пока нет данных матча. На экране матча нажмите «Анализ экрана».",
                detail="Мне нужен хотя бы один снимок экрана матча со счётом и статистикой.",
                evidence_fact_ids=[],
                missing_data=["Экран матча со статистикой"],
            )
        if self.provider:
            user = (
                _context_block(tl, facts, signals, memory or [])
                + f"\n\nВОПРОС ТРЕНЕРА: {question}\n\n"
                + ANSWER_SCHEMA
            )
            try:
                d = _extract_json(self.provider.complete(SYSTEM_PROMPT, user, MODEL_FAST, 700))
                known = {f.id for f in facts}
                return Answer(
                    short=str(d["short"])[:300],
                    detail=str(d.get("detail", "")),
                    evidence_fact_ids=[i for i in d.get("evidence_fact_ids", []) if i in known],
                    missing_data=list(d.get("missing_data", [])),
                    generated_by="llm",
                )
            except Exception as e:
                log.warning("LLM-ответ не получен: %s", e)
        return rule_answer(question, tl, facts, signals)


def rule_answer(question: str, tl: Timeline, facts: list[Fact], signals: list[Signal]) -> Answer:
    """Ответ без LLM: по ключевым словам и сработавшим правилам."""
    q = question.lower()
    recs = advisor.build(tl, signals, "quick")
    if "замен" in q or "замени" in q:
        subs = [r for r in recs if r.actions[0].kind == "substitution"]
        if subs:
            r = subs[0]
            return Answer(short=r.actions[0].text.split(". Почему")[0] + ".", detail=r.actions[0].text,
                          evidence_fact_ids=r.evidence_fact_ids, missing_data=r.missing_data)
        return Answer(short="Срочной замены не вижу.",
                      detail="Ни у кого нет одновременно усталости и падения оценки, травм нет.",
                      evidence_fact_ids=[], missing_data=["Панель состава с иконками усталости"])
    important = [s for s in signals if s.rule_id != "tactic_working"]
    if not important:
        working = next((s for s in signals if s.rule_id == "tactic_working"), None)
        if working:
            return Answer(short="Тактика работает, менять ничего не нужно.", detail=working.title,
                          evidence_fact_ids=working.fact_ids, missing_data=[])
        return Answer(short="Явных проблем по данным не вижу.",
                      detail="Правила не сработали. Для глубокого разбора нужен экран статистики и тактики.",
                      evidence_fact_ids=[], missing_data=["Экран статистики матча"])
    top = sorted(important, key=lambda s: ["critical", "warning", "info"].index(s.severity.value))[0]
    detail = "; ".join(s.title for s in important)
    if recs:
        detail += ". Совет: " + recs[0].actions[0].text
    return Answer(short=top.title + ".", detail=detail, evidence_fact_ids=top.fact_ids,
                  missing_data=recs[0].missing_data if recs else [])
