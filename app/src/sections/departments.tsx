// Отделы клуба: главное меню, спортивный директор, молодёжь, финансы, разведка, сезон, чат с отделами
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { say, useCore } from "../lib/store";
import { VERDICT_CLASS } from "../lib/ru";

export function navigate(section: string) {
  window.dispatchEvent(new CustomEvent("fm27-nav", { detail: section }));
}

function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): [T | null, string | null, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    let live = true;
    fn().then((d) => live && (setData(d), setErr(null))).catch((e) => live && (setData(null), setErr(e.message)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n]);
  return [data, err, () => setN((x) => x + 1)];
}

function NeedSave() {
  return (
    <div className="empty">
      <p>Сначала откройте сохранение («Сейв и матч»).</p>
      <p className="muted">Все отделы работают с общей базой этого сейва.</p>
    </div>
  );
}

function Err({ text, action }: { text: string; action?: JSX.Element }) {
  return <section className="card"><p>{text}</p>{action}</section>;
}

const LEVEL_DOT: Record<string, string> = { critical: "crit", warning: "warn", good: "good", info: "info", muted: "muted" };

// --- Главное меню ---
export function HomeSection() {
  const s = useCore();
  const [dash, err, reload] = useLoad(() => api.dashboard(), [s.save, s.ticks.length]);
  return (
    <div className="grid2">
      <section className="card span2">
        <h3>AI Football Department</h3>
        <p className="muted small">Девять отделов работают с одной базой сейва и передают выводы друг другу. Нажмите на отдел, чтобы открыть его.</p>
        {s.save && (
          <div className="row">
            <button className="btn" onClick={async () => { await api.clubDemoImport(); reload(); }}>Загрузить демо-выгрузки</button>
            <button className="btn btn--ghost" onClick={async () => { await api.seasonDemo(); reload(); }}>Добавить демо-сезон</button>
          </div>
        )}
      </section>
      {err && <Err text={err} />}
      {dash?.map((d: any) => (
        <section key={d.id} className="card dept" onClick={() => navigate(d.section)} role="button">
          <div className="dept__head"><h3>{d.name}</h3><span className="muted small">{d.role}</span></div>
          <ul className="dept__lines">
            {d.lines.map((l: any, i: number) => (
              <li key={i} className={`dl dl--${LEVEL_DOT[l.level] ?? "info"}`}><span className="dot" />{l.text}</li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

// --- Заключение отделов по игроку (используется в отчёте скаута) ---
export function Conclusion({ id }: { id: number }) {
  const [c, err] = useLoad(() => api.conclusion(id), [id]);
  if (err) return <p className="warn-text">{err}</p>;
  if (!c) return <p className="muted">Отделы совещаются…</p>;
  const st: Record<string, string> = { "за": "good", "против": "crit", "нейтрально": "muted" };
  return (
    <div className="conclusion">
      <p><span className={`verdict verdict--${VERDICT_CLASS[c.verdict]}`}>{c.verdict} · {c.verdict_ru}</span> <b>{c.summary}</b></p>
      <table className="tbl"><tbody>
        {c.opinions.map((o: any) => (
          <tr key={o.dept}><td className="nowrap">{o.dept}</td><td><span className={`stance stance--${st[o.stance]}`}>{o.stance}</span></td><td className="small">{o.text}</td></tr>
        ))}
      </tbody></table>
      {c.deal?.negotiation?.tips?.length > 0 && (
        <details><summary>Стратегия переговоров</summary>
          <ul>{c.deal.negotiation.tips.map((t: string, i: number) => <li key={i}>{t}</li>)}</ul>
          {c.deal.negotiation.wage_offer && <p className="small">Зарплата: {c.deal.negotiation.wage_offer.text}</p>}
        </details>
      )}
      <p className="muted small">{c.note} {c.deal?.note}</p>
    </div>
  );
}

// --- Спортивный директор: режим трансферного окна ---
const WINDOW_EXAMPLES = [
  "У нас 25 миллионов евро. Необходимо усилить центральную защиту и опорную зону",
  "Бюджет 10 млн, нужен левый защитник",
  "Определи приоритеты окна сам",
];

export function DirectorSection() {
  const s = useCore();
  const [q, setQ] = useState(WINDOW_EXAMPLES[0]);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!s.save) return <NeedSave />;
  const run = async (text: string) => {
    setQ(text); setBusy(true);
    try { setRes(await api.window(text)); setErr(null); } catch (e) { setErr((e as Error).message); setRes(null); }
    setBusy(false);
  };
  return (
    <div className="grid2">
      <section className="card span2">
        <h3>Режим трансферного окна</h3>
        <form className="ask" onSubmit={(e) => { e.preventDefault(); run(q); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Бюджет и позиции, которые нужно усилить…" />
          <button className="btn btn--primary" disabled={busy}>{busy ? "Считаю…" : "Составить план"}</button>
        </form>
        <div className="chips">{WINDOW_EXAMPLES.map((x) => <button key={x} className="chip" onClick={() => run(x)}>{x}</button>)}</div>
        {err && <p className="warn-text">{err}</p>}
        {res && (
          <div className="understood">
            <b>Бюджет {res.budget_text}</b> <span className="muted small">· позиции {res.needs_source}</span>
            <ul>{res.needs.map((n: any) => (
              <li key={n.code}>{n.name} — нужен уровень выше {n.benchmark}; кандидатов: {n.candidates.length}</li>
            ))}</ul>
          </div>
        )}
      </section>
      {res?.scenarios.map((sc: any) => (
        <section key={sc.id} className={`card scen scen--${sc.id}`}>
          <h3>{sc.title} <span className="muted small">· {sc.total_text}</span></h3>
          <p className="muted small">{sc.description}</p>
          {sc.picks.length ? (
            <table className="tbl"><tbody>{sc.picks.map((p: any) => (
              <tr key={p.id}>
                <td className="small muted">{p.need}</td><td>{p.name}, {p.age}</td>
                <td><span className="fit fit--ok">{p.fit}</span> <span className="small good-text">+{p.improvement}</span></td>
                <td>{p.price_text}</td>
                <td className="small warn-text">{p.risks.join(", ")}</td>
              </tr>
            ))}</tbody></table>
          ) : <p className="muted">Под условия никто не подходит.</p>}
          <p className="small">Остаток: {sc.left_text} · зарплаты +{sc.wages_added_text}</p>
          {sc.uncovered.length > 0 && <p className="small warn-text">Не закрыто: {sc.uncovered.join(", ")}</p>}
          {sc.sales_text && <p className="small warn-text">{sc.sales_text}</p>}
        </section>
      ))}
      {res && (
        <section className="card">
          <h3>Возможные продажи</h3>
          {res.sales.length ? (
            <table className="tbl"><tbody>{res.sales.map((v: any) => (
              <tr key={v.id}><td>{v.name}, {v.age}</td><td>{v.value}</td><td className="small">{v.why}</td></tr>
            ))}</tbody></table>
          ) : <p className="muted">Продавать некого.</p>}
          <p className="muted small">{res.note} {res.disclaimer}.</p>
        </section>
      )}
    </div>
  );
}

// --- Финансы ---
export function FinanceSection() {
  const s = useCore();
  const [f, err] = useLoad(() => (s.save ? api.finance() : Promise.resolve(null)), [s.save]);
  if (!s.save) return <NeedSave />;
  if (err) return <Err text={err} />;
  if (!f) return <div className="card muted">Загрузка…</div>;
  if (f.error) return <Err text={f.error} />;
  const List = ({ title, rows, empty }: { title: string; rows: any[]; empty: string }) => (
    <section className="card">
      <h3>{title}</h3>
      {rows.length ? <table className="tbl"><tbody>{rows.map((r: any) => (
        <tr key={r.id}><td>{r.name}{r.age ? `, ${r.age}` : ""}</td><td className="small">{r.why}</td></tr>
      ))}</tbody></table> : <p className="muted">{empty}</p>}
    </section>
  );
  return (
    <div className="grid2">
      <section className="card">
        <h3>Ведомость</h3>
        <div className="tiles">
          <div className="tile"><span className="muted small">в неделю</span><b>{f.payroll_week}</b></div>
          <div className="tile"><span className="muted small">в год</span><b>{f.payroll_year}</b></div>
          <div className="tile"><span className="muted small">медиана</span><b>{f.median_wage}</b></div>
          <div className="tile"><span className="muted small">стоимость состава</span><b>{f.squad_value}</b></div>
        </div>
        {f.budget_line && <p>{f.budget_line}</p>}
        {f.alerts.map((a: any, i: number) => <p key={i} className={a.level === "critical" ? "crit-text" : "warn-text"}>{a.text}</p>)}
      </section>
      <section className="card">
        <h3>Самые высокие зарплаты</h3>
        <table className="tbl"><tbody>{f.top_earners.map((p: any) => (
          <tr key={p.id}><td>{p.name}</td><td>{p.wage}</td><td className="muted small">{p.share} ведомости</td><td className="small">{p.role}</td></tr>
        ))}</tbody></table>
      </section>
      <List title="Продлить контракт" rows={f.renew} empty="Срочных продлений нет." />
      <List title="Продать до истечения контракта" rows={f.sell_before_expiry} empty="Таких игроков нет." />
      <List title="Переплата относительно роли" rows={f.overpaid} empty="Переплат не видно." />
      <section className="card">
        <h3>Где сэкономить</h3>
        {f.savings.length ? <ul>{f.savings.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul> : <p className="muted">Явной экономии не видно.</p>}
        <p className="muted small">{f.note}</p>
      </section>
    </div>
  );
}

// --- Молодёжь ---
const STATUS_CLASS: Record<string, string> = {
  "Готов к первой команде": "good", "Игрок основы": "good", "Ротация": "ok", "Нужна аренда": "warn", "Развитие в академии": "muted",
};

export function YouthSection() {
  const s = useCore();
  const [y, err] = useLoad(() => (s.save ? api.youth() : Promise.resolve(null)), [s.save]);
  if (!s.save) return <NeedSave />;
  if (err) return <Err text={err} />;
  if (!y) return <div className="card muted">Загрузка…</div>;
  return (
    <div className="grid2">
      <section className="card span2">
        <h3>Развитие молодёжи · игроков до 21: {y.count}</h3>
        <p className="muted small">{y.note}</p>
      </section>
      {y.players.map((p: any) => (
        <section key={p.id} className="card">
          <div className="row"><h3 style={{ margin: 0 }}>{p.name}, {p.age}</h3>
            <span className={`verdict verdict--${STATUS_CLASS[p.status] === "good" ? "good" : STATUS_CLASS[p.status] === "warn" ? "warn" : "muted"}`}>{p.status}</span></div>
          <p className="small muted">{p.position} · {p.profile}</p>
          <p>Соответствие <span className="fit fit--ok">{p.fit ?? "н/д"}</span>
            {p.starter_fit !== null && <span className="small"> · основной на позиции {p.starter_fit} ({p.gap >= 0 ? "+" : ""}{p.gap})</span>}</p>
          <p className="small">{p.development.text}</p>
          {p.development.grown?.length > 0 && <p className="small good-text">Рост: {p.development.grown.join(", ")}</p>}
          {p.flags.map((f: string, i: number) => <p key={i} className="small warn-text">{f}</p>)}
          <h4>Индивидуальный план развития</h4>
          <table className="tbl tbl--kv"><tbody>
            {["technical", "physical", "mental", "goalkeeping", "tactical"].filter((g) => p.plan[g]).map((g) => (
              <tr key={g}><td>{p.plan[g].title}</td><td className="small">{p.plan[g].focus.join(", ")}{p.plan[g].note ? <span className="muted"> — {p.plan[g].note}</span> : null}</td></tr>
            ))}
          </tbody></table>
          <ul className="small">{p.actions.map((a: string, i: number) => <li key={i}>{a}</li>)}</ul>
        </section>
      ))}
    </div>
  );
}

// --- Разведка соперника ---
export function ReconSection() {
  const s = useCore();
  const [list, , reloadList] = useLoad(() => (s.save ? api.oppList() : Promise.resolve([])), [s.save]);
  const [scope, setScope] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const current = scope ?? list?.[0]?.scope ?? null;
  const [rep, err] = useLoad(() => (current ? api.oppReport(current) : Promise.resolve(null)), [current]);
  if (!s.save) return <NeedSave />;
  const TYPE: Record<string, string> = { attack: "Как атаковать", defend: "Как нейтрализовать угрозы", set_piece: "Стандарты" };
  return (
    <div className="grid2">
      <section className="card">
        <h3>Выгрузка состава соперника</h3>
        <p className="muted small">Откройте в FM27 состав соперника и выгрузите его (F8 в FM27 Exporter, с атрибутами).</p>
        <div className="row">
          <input className="inp" value={name} onChange={(e) => setName(e.target.value)} placeholder="Название соперника" />
          <label className={`btn ${name ? "" : "btn--disabled"}`}>Файл…<input type="file" hidden accept=".csv,.html,.htm,.txt" disabled={!name}
            onChange={async (e) => {
              const f = e.target.files?.[0]; if (!f) return;
              try { const r = await api.oppImport(name, f.name, await f.text()); setMsg(`${f.name}: ${r.added + r.updated} игроков`); setScope(r.scope); reloadList(); }
              catch (x) { setMsg((x as Error).message); }
            }} /></label>
        </div>
        {msg && <p className="small">{msg}</p>}
      </section>
      <section className="card">
        <h3>Соперники в базе</h3>
        {list?.length ? (
          <div className="chips">{list.map((o: any) => (
            <button key={o.scope} className={`chip ${o.scope === current ? "chip--on" : ""}`} onClick={() => setScope(o.scope)}>{o.name}</button>
          ))}</div>
        ) : <p className="muted">Пока нет. В «Главном меню» можно загрузить демо-соперника.</p>}
      </section>
      {err && <Err text={err} />}
      {rep && (
        <>
          <section className="card span2">
            <h3>Opposition Scouting Report · {rep.opponent}</h3>
            <p><b>Вероятная схема:</b> {rep.formation_text}</p>
            <p className="small">{rep.lineup_guess.map((x: any) => `${x.label} ${x.name}`).join(" · ")}</p>
            <p className="muted small">{rep.note}</p>
          </section>
          <section className="card">
            <h3>Подтверждено данными</h3>
            <ul className="small">{rep.facts.map((f: string, i: number) => <li key={i}>{f}</li>)}</ul>
            {rep.past_matches.length > 0 && <p className="small">Прошлые матчи: {rep.past_matches.map((m: any) => `${m.score} (${m.home ? "дома" : "в гостях"})`).join(", ")}</p>}
          </section>
          <section className="card">
            <h3>Тактические гипотезы</h3>
            {["attack", "defend", "set_piece"].map((t) => {
              const hs = rep.hypotheses.filter((h: any) => h.type === t);
              return hs.length ? (
                <div key={t}><h4>{TYPE[t]}</h4><ul className="small">{hs.map((h: any, i: number) => <li key={i}>{h.text}</li>)}</ul></div>
              ) : null;
            })}
            <h4>Стандарты соперника</h4>
            <ul className="small">{rep.set_pieces.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            <p className="muted small">Без данных: {rep.unknown.join(", ").toLowerCase()} — нужен экран превью/анализа соперника.</p>
          </section>
        </>
      )}
    </div>
  );
}

// --- Сезон ---
export function SeasonSection() {
  const s = useCore();
  const [r, err, reload] = useLoad(() => (s.save ? api.season() : Promise.resolve(null)), [s.save]);
  const [form, setForm] = useState({ opponent: "", our_side: "home", goals_for: "", goals_against: "", game_date: "", xg_for: "", xg_against: "" });
  if (!s.save) return <NeedSave />;
  const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));
  const addResult = (
    <section className="card">
      <h3>Добавить итог матча</h3>
      <p className="muted small">Если матч не отслеживался помощником вживую.</p>
      <div className="formrow">
        <input className="inp" placeholder="Соперник" value={form.opponent} onChange={(e) => setForm({ ...form, opponent: e.target.value })} />
        <select className="inp" value={form.our_side} onChange={(e) => setForm({ ...form, our_side: e.target.value })}><option value="home">дома</option><option value="away">в гостях</option></select>
        <input className="inp inp--s" placeholder="Мы" value={form.goals_for} onChange={(e) => setForm({ ...form, goals_for: e.target.value })} />
        <input className="inp inp--s" placeholder="Они" value={form.goals_against} onChange={(e) => setForm({ ...form, goals_against: e.target.value })} />
        <input className="inp inp--s" placeholder="xG мы" value={form.xg_for} onChange={(e) => setForm({ ...form, xg_for: e.target.value })} />
        <input className="inp inp--s" placeholder="xG они" value={form.xg_against} onChange={(e) => setForm({ ...form, xg_against: e.target.value })} />
        <input className="inp" type="date" value={form.game_date} onChange={(e) => setForm({ ...form, game_date: e.target.value })} />
        <button className="btn btn--primary" disabled={!form.opponent || form.goals_for === "" || form.goals_against === ""} onClick={async () => {
          await api.seasonResult({ opponent: form.opponent, our_side: form.our_side, goals_for: Number(form.goals_for), goals_against: Number(form.goals_against),
            game_date: form.game_date || null, xg_for: num(form.xg_for), xg_against: num(form.xg_against) });
          setForm({ ...form, opponent: "", goals_for: "", goals_against: "", xg_for: "", xg_against: "" }); reload();
        }}>Добавить</button>
      </div>
      <button className="btn btn--ghost" onClick={async () => { await api.seasonDemo(); reload(); }}>Добавить демо-сезон (18 матчей)</button>
    </section>
  );
  if (err) return <div className="grid2"><Err text={err} />{addResult}</div>;
  if (!r) return <div className="card muted">Загрузка…</div>;
  if (r.error) return <div className="grid2"><Err text={r.error} />{addResult}</div>;
  const t = r.total;
  return (
    <div className="grid2">
      <section className="card span2">
        <h3>Сезон</h3>
        <div className="tiles">
          <div className="tile"><span className="muted small">матчи</span><b>{t.played}</b></div>
          <div className="tile"><span className="muted small">В–Н–П</span><b>{t.w}–{t.d}–{t.l}</b></div>
          <div className="tile"><span className="muted small">очки</span><b>{t.pts}</b></div>
          <div className="tile"><span className="muted small">очков за матч</span><b>{t.ppg}</b></div>
          <div className="tile"><span className="muted small">голы</span><b>{t.gf}:{t.ga}</b></div>
          <div className="tile"><span className="muted small">xG</span><b>{t.xg_for ?? "—"}:{t.xg_against ?? "—"}</b></div>
          <div className="tile"><span className="muted small">форма</span><b className="form">{r.form}</b></div>
          <div className="tile"><span className="muted small">дома / в гостях</span><b>{r.home.ppg} / {r.away.ppg}</b></div>
        </div>
      </section>
      <section className="card">
        <h3>Где теряем очки</h3>
        {r.points_lost.length ? <ol>{r.points_lost.map((i: any) => <li key={i.id}>{i.text} <span className="muted small">(~{i.points} очк.)</span></li>)}</ol>
          : <p className="muted">Системных потерь не видно.</p>}
        <h4>Что исправить в следующем месяце</h4>
        <ul>{r.next_focus.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
      </section>
      <section className="card">
        <h3>По месяцам</h3>
        <table className="tbl"><thead><tr><th>Период</th><th>Результаты</th><th>Очки/матч</th><th>Голы</th><th>xG ±/матч</th></tr></thead>
          <tbody>{r.periods.map((p: any) => (
            <tr key={p.title}><td>{p.title}</td><td className="form">{p.results}</td><td>{p.ppg}</td><td>{p.gf}:{p.ga}</td><td>{p.xg_diff_pm ?? "—"}</td></tr>
          ))}</tbody></table>
      </section>
      <section className="card">
        <h3>Какая тактика работает</h3>
        <table className="tbl"><thead><tr><th>Наша схема</th><th>Матчи</th><th>Очки/матч</th><th>xG ±/матч</th></tr></thead>
          <tbody>{r.by_formation.map((f: any) => <tr key={f.formation}><td>{f.formation}</td><td>{f.played}</td><td>{f.ppg}</td><td>{f.xg_diff_pm ?? "—"}</td></tr>)}</tbody></table>
        <h4>Против разных соперников</h4>
        <table className="tbl"><tbody>
          {r.opp_types.map((o: any) => <tr key={o.type}><td className="small">{o.type}</td><td>{o.played} матч.</td><td>{o.ppg ?? "—"} очк./матч</td></tr>)}
          {r.by_opp_formation.map((o: any) => <tr key={o.opp_formation}><td className="small">Соперник в {o.opp_formation}</td><td>{o.played} матч.</td><td>{o.ppg} очк./матч</td></tr>)}
        </tbody></table>
      </section>
      <section className="card">
        <h3>Самые важные игроки</h3>
        <table className="tbl"><tbody>{r.players.map((p: any) => (
          <tr key={p.name}><td>{p.name}</td><td className="muted small">{p.position}</td><td>{p.avg}</td><td className="muted small">{p.matches} матч.</td></tr>
        ))}</tbody></table>
        <p className="muted small">{r.note}</p>
        <h4>Какие изменения помогли</h4>
        {r.changes.length ? <ul>{r.changes.map((c: any) => <li key={c.change}>{c.change}: xG-баланс {c.xg_diff > 0 ? "+" : ""}{c.xg_diff} за 15 мин ({c.times} раз)</li>)}</ul>
          : <p className="muted small">Принятых советов с оценкой эффекта пока нет — они появятся после матчей с помощником.</p>}
      </section>
      {addResult}
    </div>
  );
}

// --- AI-чат с отделами ---
const DEPT_QUICK = [
  "Почему команда теряет очки?",
  "У нас 25 миллионов. Нужно усилить центральную защиту и опорную зону",
  "Каким игрокам продлить контракт?",
  "Кто из молодых готов к основе?",
  "Как нейтрализовать соперника?",
  "Какие слабые позиции в составе?",
];

export function DeptChatSection() {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<any[]>([]);
  const send = async (text: string) => {
    if (!text.trim()) return;
    setQ("");
    try { const r = await api.deptAsk(text.trim()); setItems((xs) => [r, ...xs].slice(0, 30)); say(r.short); }
    catch (e) { setItems((xs) => [{ question: text, short: (e as Error).message, detail: "", department_name: "Ошибка" }, ...xs]); }
  };
  return (
    <section className="card chat">
      <p className="muted small">Вопрос автоматически попадает в нужный отдел. Во время матча вопросы о текущей игре отвечает аналитик матча.</p>
      <div className="chips">{DEPT_QUICK.map((x) => <button key={x} className="chip" onClick={() => send(x)}>{x}</button>)}</div>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); send(q); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Спросите штаб клуба…" />
        <button className="btn btn--primary" type="submit">Спросить</button>
      </form>
      <div className="answers">
        {items.map((a, i) => (
          <article key={i} className="answer">
            <p className="answer__q">{a.question}</p>
            <p className="answer__dept">{a.department_name}{a.section && <button className="btn btn--ghost btn--xs" onClick={() => navigate(a.section)}>открыть отдел</button>}</p>
            <p className="answer__short">{a.short}</p>
            {a.detail && a.detail !== a.short && <p className="answer__detail small">{a.detail}</p>}
          </article>
        ))}
      </div>
    </section>
  );
}
