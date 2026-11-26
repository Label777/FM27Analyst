"""HTTP-эндпоинты отделов клуба: импорт, ДНК, скаут, состав."""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import demo_data
from .db import ClubDB, ClubDNA
from .fit import best_fit
from .importer import ScoutPlayer, import_table
from .report import compare, money, scouting_report, wonderkids
from .search import parse_query, parse_query_llm, run_search
from .squad import squad_plan
from .values import POSITION_RU


class ImportIn(BaseModel):
    filename: str
    content: str
    scope: str = "market"  # own | market | opp:<соперник>
    replace: bool = False


class OppImportIn(BaseModel):
    name: str
    filename: str
    content: str


class WindowIn(BaseModel):
    query: str | None = None
    budget: float | None = None
    needs: list[list[str]] | None = None


class ResultIn(BaseModel):
    opponent: str
    our_side: Literal["home", "away"] = "home"
    goals_for: int
    goals_against: int
    game_date: str | None = None
    xg_for: float | None = None
    xg_against: float | None = None
    possession: float | None = None
    our_formation: str | None = None
    opp_formation: str | None = None


class AskDeptIn(BaseModel):
    question: str


def opp_scope(name: str) -> str:
    from ..storage import slugify

    return "opp:" + slugify(name)


class SearchIn(BaseModel):
    query: str


class CompareIn(BaseModel):
    ids: list[int]


def summary(p: ScoutPlayer, dna: ClubDNA, position: str | None = None) -> dict:
    fit = best_fit(p, dna, position)
    return {
        "id": p.id, "name": p.name, "age": p.age, "club": p.club, "division": p.division,
        "positions": [POSITION_RU.get(x, x) for x in p.positions], "position_raw": p.position_raw,
        "value": money(p.value_mid, p.currency), "value_num": p.value_mid, "wage": money(p.wage_week, p.currency),
        "contract": p.contract_until.isoformat() if p.contract_until else None,
        "current_stars": p.current_stars, "potential_stars": p.potential_stars,
        "fit": fit.score if fit else None, "fit_profile": fit.profile_name if fit else None,
        "fit_confidence": fit.confidence if fit else 0, "free_agent": p.is_free_agent(),
        "source": p.source.file,
    }


def register(app: FastAPI, engine) -> None:
    cache: dict[str, ClubDB] = {}

    def club() -> ClubDB:
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение — база клуба хранится в файле сейва")
        sid = engine.store.save_id
        if sid not in cache or cache[sid].db is not engine.store.db:
            cache[sid] = ClubDB(engine.store.db)
        return cache[sid]

    @app.post("/api/club/import")
    def do_import(body: ImportIn) -> dict:
        if body.scope not in ("own", "market") and not body.scope.startswith("opp:"):
            raise HTTPException(422, "scope: own, market или opp:<соперник>")
        res = import_table(body.content, body.filename, scope=body.scope)
        if not res.players:
            raise HTTPException(422, "; ".join(res.warnings) or "Игроки не найдены")
        stats = club().save_import(res, body.scope, body.filename, replace_scope=body.replace)
        return {**stats, "rows": len(res.players), "mapped": res.mapped}

    @app.post("/api/club/demo-import")
    def demo_import() -> dict:
        """Демо: рынок, состав (две выгрузки с разницей 6 мес. — для динамики молодёжи), соперник."""
        from datetime import date as _date

        c = club()
        out = {}
        d0, d1 = _date(2026, 7, 15), _date(2027, 1, 15)
        res = import_table(demo_data.market_export(), "demo_player_search.html", scope="market", kind="demo")
        out["market"] = c.save_import(res, "market", "demo_player_search.html", replace_scope=True, game_date=d1)
        res = import_table(demo_data.squad_export(), "demo_squad_jul.html", scope="own", kind="demo")
        c.save_import(res, "own", "demo_squad_jul.html", replace_scope=True, game_date=d0)
        res = import_table(demo_data.squad_export_later(), "demo_squad_jan.html", scope="own", kind="demo")
        out["own"] = c.save_import(res, "own", "demo_squad_jan.html", game_date=d1)
        scope = opp_scope("ФК Соперник (демо)")
        res = import_table(demo_data.opponent_export(), "demo_opponent.html", scope=scope, kind="demo")
        out["opponent"] = c.save_import(res, scope, "demo_opponent.html", replace_scope=True, game_date=d1)
        c.db.execute("INSERT OR REPLACE INTO meta_opp (scope, name) VALUES (?, ?)", (scope, "ФК Соперник (демо)"))
        c.db.commit()
        dna = c.dna()
        if dna.transfer_budget is None:
            dna = ClubDNA(style=["high_fullbacks", "high_press"], transfer_budget=15e6, max_signing_age=27,
                          wage_budget_total_week=600e3)
        dna.game_date = d1
        c.set_dna(dna)
        return out

    @app.get("/api/club/imports")
    def imports() -> list[dict]:
        return club().imports()

    @app.get("/api/club/players")
    def players(scope: Literal["own", "market"] = "own") -> list[dict]:
        c = club()
        dna = c.dna()
        return [summary(p, dna) for p in c.players(scope)]

    @app.get("/api/club/dna")
    def get_dna() -> dict:
        return club().dna().model_dump(mode="json")

    @app.put("/api/club/dna")
    def put_dna(dna: ClubDNA) -> dict:
        club().set_dna(dna)
        return dna.model_dump(mode="json")

    @app.post("/api/scout/search")
    def search(body: SearchIn) -> dict:
        c = club()
        dna = c.dna()
        parsed = None
        provider = getattr(engine.reasoner, "provider", None)
        if provider is not None:
            parsed = parse_query_llm(body.query, provider)
        f, understood = parsed or parse_query(body.query)
        market = c.players("market")
        if not market:
            raise HTTPException(409, "База рынка пуста: импортируйте выгрузку поиска игроков из FM27")
        hits = run_search(market, f, dna)
        pos = f.positions[0] if f.positions else None
        return {
            "understood": understood,
            "filters": f.model_dump(),
            "parsed_by": "llm" if parsed else "rules",
            "pool": len(market),
            "hits": [{**summary(h.player, dna, next((x for x in f.positions if x in h.player.positions), pos)),
                      "reasons": h.reasons} for h in hits],
        }

    @app.get("/api/scout/report/{pid}")
    def report(pid: int) -> dict:
        c = club()
        p = c.player(pid)
        if p is None:
            raise HTTPException(404, "Игрок не найден")
        return scouting_report(p, c.dna(), c.players("own"), c.players("market"), c.attribute_history(p.key))

    @app.post("/api/scout/compare")
    def do_compare(body: CompareIn) -> dict:
        c = club()
        ps = [p for i in body.ids if (p := c.player(i))]
        if len(ps) < 2:
            raise HTTPException(422, "Выберите хотя бы двух игроков")
        return compare(ps, c.dna(), c.players("own"), c.players("market"))

    @app.get("/api/scout/wonderkids")
    def wk() -> dict:
        c = club()
        return wonderkids(c.players("market"), c.dna())

    @app.get("/api/squad/plan")
    def plan() -> dict:
        c = club()
        own = c.players("own")
        if not own:
            raise HTTPException(409, "Состав не импортирован: выгрузите экран состава из FM27")
        return squad_plan(own, c.dna())

    @app.get("/api/scout/shortlist")
    def shortlist() -> list[dict]:
        c = club()
        dna = c.dna()
        return [summary(p, dna) for i in c.shortlist() if (p := c.player(i))]

    @app.post("/api/scout/shortlist/{pid}")
    def shortlist_add(pid: int) -> dict:
        club().shortlist_add(pid)
        return {"ok": True}

    @app.delete("/api/scout/shortlist/{pid}")
    def shortlist_del(pid: int) -> dict:
        club().shortlist_remove(pid)
        return {"ok": True}


def register_departments(app: FastAPI, engine) -> None:
    from .. import departments
    from ..season import add_result, demo_season, season_answer, season_report
    from .director import assess_deal, parse_window_request, transfer_window
    from .finance import finance_report
    from .opposition import opposition_report
    from .youth import youth_report

    def club() -> ClubDB:
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение — база клуба хранится в файле сейва")
        return ClubDB(engine.store.db)

    def own_or_409(c: ClubDB) -> list[ScoutPlayer]:
        own = c.players("own")
        if not own:
            raise HTTPException(409, "Состав не импортирован: выгрузите экран состава из FM27")
        return own

    # --- спортивный директор ---
    @app.get("/api/director/deal/{pid}")
    def deal(pid: int) -> dict:
        c = club()
        p = c.player(pid)
        if p is None:
            raise HTTPException(404, "Игрок не найден")
        return assess_deal(p, c.dna(), c.players("own"), c.players("market"))

    @app.post("/api/director/window")
    def window(body: WindowIn) -> dict:
        c = club()
        budget, needs, understood = body.budget, body.needs, []
        if body.query:
            req = parse_window_request(body.query)
            budget = budget or req["budget"]
            needs = needs or req["needs"] or None
            if req["budget"]:
                understood.append(f"Бюджет: {money(req['budget'], c.dna().currency)}")
            if req["needs"]:
                understood.append("Позиции: " + ", ".join(POSITION_RU.get(n[0], n[0]) for n in req["needs"]))
        market = c.players("market")
        if not market:
            raise HTTPException(409, "База рынка пуста — импортируйте поиск игроков")
        res = transfer_window(c.dna(), c.players("own"), market, budget, needs)
        if "error" in res:
            raise HTTPException(422, res["error"])
        return {**res, "understood": understood}

    # --- финансы и молодёжь ---
    @app.get("/api/finance/report")
    def finance() -> dict:
        c = club()
        return finance_report(own_or_409(c), c.dna())

    @app.get("/api/youth/report")
    def youth() -> dict:
        c = club()
        return youth_report(own_or_409(c), c.dna(), c.attribute_history_full)

    # --- разведка соперника ---
    @app.post("/api/opposition/import")
    def opp_import(body: OppImportIn) -> dict:
        c = club()
        scope = opp_scope(body.name)
        res = import_table(body.content, body.filename, scope=scope)
        if not res.players:
            raise HTTPException(422, "; ".join(res.warnings) or "Игроки не найдены")
        stats = c.save_import(res, scope, body.filename, replace_scope=True)
        c.db.execute("INSERT OR REPLACE INTO meta_opp (scope, name) VALUES (?, ?)", (scope, body.name))
        c.db.commit()
        return {**stats, "scope": scope}

    @app.get("/api/opposition/list")
    def opp_list() -> list[dict]:
        c = club()
        names = dict(c.db.execute("SELECT scope, name FROM meta_opp").fetchall())
        return [{"scope": s, "name": names.get(s, s[4:])} for s in c.scopes() if s.startswith("opp:")]

    @app.get("/api/opposition/report")
    def opp_report(scope: str) -> dict:
        c = club()
        names = dict(c.db.execute("SELECT scope, name FROM meta_opp").fetchall())
        players = c.players(scope)
        if not players:
            raise HTTPException(404, "Нет выгрузки этого соперника")
        name = names.get(scope, scope[4:])
        past = []
        if engine.store:
            from ..season import load

            past = [{"result": m["result"], "score": f"{m['gf']}:{m['ga']}", "home": m["home"],
                     "xg": [m["xg_for"], m["xg_against"]], "date": m["game_date"]}
                    for m in load(engine.store) if m["opponent"].lower() == name.lower()]
        return opposition_report(name, players, c.players("own"), c.dna(), past)

    # --- сезон ---
    @app.get("/api/season/report")
    def season() -> dict:
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение")
        return season_report(engine.store)

    @app.post("/api/season/result")
    def result(body: ResultIn) -> dict:
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение")
        mid = add_result(engine.store, body.opponent, body.our_side, body.goals_for, body.goals_against,
                         game_date=body.game_date, xg_for=body.xg_for, xg_against=body.xg_against,
                         possession=body.possession, our_formation=body.our_formation, opp_formation=body.opp_formation)
        return {"match_id": mid}

    @app.post("/api/season/demo")
    def season_demo() -> dict:
        if engine.store is None:
            raise HTTPException(409, "Сначала выберите сохранение")
        return {"matches": demo_season(engine.store)}

    # --- главное меню и оркестратор ---
    @app.get("/api/department/dashboard")
    def dash() -> list[dict]:
        return departments.dashboard(engine, ClubDB(engine.store.db) if engine.store else None)

    @app.get("/api/department/player/{pid}")
    def conclusion(pid: int) -> dict:
        try:
            return departments.player_conclusion(club(), pid)
        except KeyError as e:
            raise HTTPException(404, "Игрок не найден") from e

    @app.post("/api/department/ask")
    def dept_ask(body: AskDeptIn) -> dict:
        return departments.ask(engine, ClubDB(engine.store.db) if engine.store else None, body.question)
