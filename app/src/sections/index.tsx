import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { actions, latest, useCore } from "../lib/store";
import { ATTR, FATIGUE, fmt, them, us } from "../lib/ru";
import type { HistoryItem, MatchRow, PlayerState } from "../lib/types";
import { RecCard, Scoreboard, SignalList, StatBars, XgChart } from "../components";

function Empty() {
  return (
    <div className="empty">
      <p>Данных матча пока нет.</p>
      <p className="muted">Откройте сохранение и начните матч, затем на экране матча нажмите «Анализ экрана» — или запустите демо.</p>
    </div>
  );
}

export function LiveSection() {
  const s = useCore();
  const t = latest(s);
  if (!t) return <Empty />;
  const facts = t.facts;
  const open = [...s.recs].reverse();
  return (
    <div className="grid2">
      <section className="card">
        <Scoreboard snap={t.snapshot} />
        <StatBars snap={t.snapshot} />
      </section>
      <section className="card">
        <h3>Предупреждения</h3>
        <SignalList signals={t.signals} />
        {t.changes.length > 0 && (
          <>
            <h4>Что изменилось с прошлого снимка</h4>
            <ul className="changes">{t.changes.map((c, i) => <li key={i}>{c.text}</li>)}</ul>
          </>
        )}
      </section>
      <section className="card span2">
        <h3>xG по ходу матча</h3>
        <XgChart ticks={s.ticks} />
      </section>
      <section className="card span2">
        <h3>Рекомендации</h3>
        {open.length ? open.map((r) => <RecCard key={r.id + r.minute} rec={r} facts={facts} />) : (
          <p className="muted">Советов нет — менять ничего не нужно, пока правила не видят проблем.</p>
        )}
      </section>
    </div>
  );
}

export function TacticsSection() {
  const s = useCore();
  const t = latest(s);
  if (!t) return <Empty />;
  const o = us(t.snapshot);
  const p = them(t.snapshot);
  const tactical = t.signals.filter((x) => !x.player);
  return (
    <div className="grid2">
      <section className="card">
        <h3>Наша схема</h3>
        <dl className="kv">
          <dt>В владении</dt><dd>{o.formation_in_possession ?? "—"}</dd>
          <dt>Без мяча</dt><dd>{o.formation_out_of_possession ?? "—"}</dd>
        </dl>
        <p className="muted small">Роли игроков появятся после снимка экрана тактики (этап 3).</p>
      </section>
      <section className="card">
        <h3>Схема соперника</h3>
        <dl className="kv">
          <dt>В владении</dt><dd>{p.formation_in_possession ?? "—"}</dd>
          <dt>Без мяча</dt><dd>{p.formation_out_of_possession ?? "—"}</dd>
        </dl>
      </section>
      <section className="card span2">
        <h3>Тактическая эффективность</h3>
        <SignalList signals={tactical} />
        <div className="row">
          <button className="btn btn--primary" onClick={() => actions.review()}>Глубокий разбор (режим «Главный тренер»)</button>
        </div>
        {s.review.map((r, i) => <RecCard key={i} rec={r} facts={t.facts} />)}
      </section>
    </div>
  );
}

function trend(name: string, ticks: ReturnType<typeof useCore>["ticks"]) {
  return ticks
    .map((t) => us(t.snapshot).players.find((p) => p.name === name)?.rating)
    .filter((r): r is number => typeof r === "number")
    .slice(-4);
}

export function PlayersSection() {
  const s = useCore();
  const t = latest(s);
  if (!t) return <Empty />;
  const flagged = new Set(t.signals.filter((x) => x.player).map((x) => x.player));
  return (
    <section className="card">
      <h3>Игроки на поле</h3>
      <table className="tbl">
        <thead>
          <tr><th>Игрок</th><th>Поз.</th><th>Оценка</th><th>Тренд</th><th>Усталость</th><th>Отметки</th></tr>
        </thead>
        <tbody>
          {us(t.snapshot).players.filter((p) => p.on_pitch).map((p) => {
            const tr = trend(p.name, s.ticks);
            const down = tr.length >= 2 && tr[tr.length - 1] < tr[0];
            return (
              <tr key={p.name} className={flagged.has(p.name) ? "flag" : ""}>
                <td>{p.name}</td>
                <td>{p.position ?? "—"}</td>
                <td>{fmt(p.rating, 1)}</td>
                <td className={down ? "down" : ""}>{tr.length >= 2 ? tr.map((r) => r.toFixed(1)).join(" → ") : "—"}</td>
                <td><span className={`fat fat--${p.fatigue}`}>{FATIGUE[p.fatigue]}</span></td>
                <td>{[p.yellow_card && "ЖК", p.injured && "травма"].filter(Boolean).join(", ") || ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="muted small">Выводы не строятся только на оценке: правило «падение оценки» срабатывает вместе с усталостью или трендом за 3 снимка.</p>
    </section>
  );
}

export function OpponentSection() {
  const s = useCore();
  const t = latest(s);
  if (!t) return <Empty />;
  const forms = s.ticks
    .map((x) => ({ m: x.snapshot.minute, f: them(x.snapshot).formation_in_possession }))
    .filter((x, i, arr) => x.f && (i === 0 || arr[i - 1].f !== x.f));
  const msgs = Array.from(new Set(s.ticks.flatMap((x) => x.snapshot.dugout_messages)));
  return (
    <div className="grid2">
      <section className="card">
        <h3>Схема соперника по ходу матча</h3>
        <ul className="changes">{forms.map((x) => <li key={x.m}>{x.m}' — {x.f}</li>)}</ul>
      </section>
      <section className="card">
        <h3>Сообщения штаба (dugout)</h3>
        {msgs.length ? <ul className="changes">{msgs.map((m) => <li key={m}>{m}</li>)}</ul> : <p className="muted">Сообщений нет.</p>}
      </section>
      <section className="card span2">
        <h3>Статистика соперника</h3>
        <StatBars snap={t.snapshot} />
        <p className="muted small">Опасные игроки и зоны атак — по тепловым картам и Action Zones (этап 3).</p>
      </section>
    </div>
  );
}

function BenchRow({ p }: { p: PlayerState }) {
  const attrs = Object.entries(p.attributes);
  return (
    <tr>
      <td>{p.name}</td>
      <td>{p.position ?? "—"}</td>
      <td>{attrs.length ? attrs.map(([k, v]) => `${ATTR[k] ?? k} ${v}`).join(", ") : <span className="muted">не сняты</span>}</td>
    </tr>
  );
}

export function SubsSection() {
  const s = useCore();
  const t = latest(s);
  if (!t) return <Empty />;
  const subs = s.recs.filter((r) => r.actions.some((a) => a.kind === "substitution")).reverse();
  return (
    <div className="grid2">
      <section className="card span2">
        <h3>Рекомендованные замены</h3>
        {subs.length ? subs.map((r) => <RecCard key={r.id} rec={r} facts={t.facts} />) : <p className="muted">Срочных замен нет.</p>}
      </section>
      <section className="card span2">
        <h3>Скамейка</h3>
        <table className="tbl">
          <thead><tr><th>Игрок</th><th>Поз.</th><th>Ключевые атрибуты</th></tr></thead>
          <tbody>{us(t.snapshot).bench.map((p) => <BenchRow key={p.name} p={p} />)}</tbody>
        </table>
      </section>
    </div>
  );
}

export function HistorySection() {
  const s = useCore();
  const [matches, setMatches] = useState<MatchRow[]>([]);
  const [items, setItems] = useState<HistoryItem[]>([]);
  useEffect(() => {
    if (!s.save) return;
    api.matches().then(setMatches).catch(() => setMatches([]));
    api.history().then(setItems).catch(() => setItems([]));
  }, [s.save, s.recs.length, s.match]);
  if (!s.save) return <Empty />;
  return (
    <div className="grid2">
      <section className="card">
        <h3>Матчи сейва «{s.save.save_name}»</h3>
        <table className="tbl">
          <thead><tr><th>#</th><th>Соперник</th><th>Где</th><th>Счёт</th></tr></thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.id}><td>{m.id}</td><td>{m.opponent}</td><td>{m.our_side === "home" ? "дома" : "в гостях"}</td><td>{m.final_score ?? (m.finished ? "—" : "идёт")}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h3>Что сработало</h3>
        <table className="tbl">
          <thead><tr><th>Мин.</th><th>Совет</th><th>Статус</th><th>Через 15 мин</th></tr></thead>
          <tbody>
            {items.slice().reverse().map((h) => (
              <tr key={h.recommendation.id}>
                <td>{h.recommendation.minute}'</td>
                <td>{h.recommendation.actions[0].text.split(". Почему")[0]}</td>
                <td>{h.recommendation.status === "accepted" ? "принят" : h.recommendation.status === "rejected" ? "отклонён" : "—"}</td>
                <td>{h.outcome ? `xG ${h.outcome.xg_us >= 0 ? "+" : ""}${h.outcome.xg_us} / ${h.outcome.xg_them >= 0 ? "+" : ""}${h.outcome.xg_them}, голы ${h.outcome.goals}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">Итог одного матча — корреляция, не доказательство. Выводы — по 10+ матчам.</p>
      </section>
    </div>
  );
}

const QUICK = [
  "Что сейчас происходит с нашей тактикой?",
  "Почему мы проигрываем центр поля?",
  "Кого лучше заменить?",
  "Что изменить, чтобы создавать больше моментов?",
];

export function ChatSection() {
  const s = useCore();
  const [q, setQ] = useState("");
  const send = (text: string) => {
    if (!text.trim()) return;
    actions.ask(text.trim());
    setQ("");
  };
  return (
    <section className="card chat">
      <div className="chips">{QUICK.map((x) => <button key={x} className="chip" onClick={() => send(x)}>{x}</button>)}</div>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); send(q); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Спросите ассистента… (голосовой ввод — этап 6)" />
        <button className="btn btn--primary" type="submit">Спросить</button>
      </form>
      <div className="answers">
        {s.answers.map((a, i) => (
          <article key={i} className="answer">
            <p className="answer__q">{a.question}</p>
            <p className="answer__short">{a.short}</p>
            {a.detail && a.detail !== a.short && <p className="answer__detail">{a.detail}</p>}
            {a.missing_data.length > 0 && <p className="muted small">Нужно: {a.missing_data.join("; ")}</p>}
          </article>
        ))}
      </div>
    </section>
  );
}
