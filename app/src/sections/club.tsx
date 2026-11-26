// Отделы клуба: главный скаут, таланты, состав, ДНК клуба
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useCore } from "../lib/store";
import { FORMATIONS, STYLES, VERDICT_CLASS } from "../lib/ru";
import { Conclusion } from "./departments";

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
  return [data, err, () => setN(n + 1)];
}

function NeedSave() {
  return (
    <div className="empty">
      <p>Сначала откройте сохранение («Сейв и матч»).</p>
      <p className="muted">База клуба — игроки, ДНК, шорт-лист — хранится отдельно для каждого сейва.</p>
    </div>
  );
}

function Stars({ v }: { v: [number, number] | null }) {
  if (!v) return <span className="muted">—</span>;
  return <span>{v[0] === v[1] ? `${v[0]}★` : `${v[0]}–${v[1]}★`}</span>;
}

function FitBadge({ score, conf }: { score: number | null; conf?: number }) {
  if (score === null || score === undefined) return <span className="muted" title="Недостаточно атрибутов">н/д</span>;
  const cls = score >= 80 ? "good" : score >= 65 ? "ok" : score >= 55 ? "warn" : "crit";
  return (
    <span className={`fit fit--${cls}`} title={conf !== undefined ? `Достоверность ${(conf * 100).toFixed(0)}%` : ""}>
      {score}{conf !== undefined && conf < 0.6 ? " ~" : ""}
    </span>
  );
}

// --- Импорт выгрузок ---
function ImportPanel({ onDone }: { onDone: () => void }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [warn, setWarn] = useState<string[]>([]);
  const upload = async (file: File, scope: "own" | "market") => {
    try {
      const text = await file.text();
      const r = await api.clubImport(file.name, text, scope, scope === "own");
      setMsg(`${file.name}: ${r.rows} игроков (новых ${r.added}, обновлено ${r.updated})`);
      setWarn(r.warnings ?? []);
      onDone();
    } catch (e) {
      setMsg((e as Error).message);
      setWarn([]);
    }
  };
  return (
    <section className="card">
      <h3>Импорт выгрузок из FM27</h3>
      <p className="muted small">
        Выгрузите список плагином FM27 Exporter (F8 в игре, Ctrl+F8 — добавить все атрибуты в вид) или FM-View-Exporter (F9).
        Подходят CSV и HTML.
      </p>
      <div className="row">
        <label className="btn">Наш состав…<input type="file" accept=".csv,.html,.htm,.txt" hidden
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], "own")} /></label>
        <label className="btn">Поиск игроков / рынок…<input type="file" accept=".csv,.html,.htm,.txt" hidden
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], "market")} /></label>
        <button className="btn btn--ghost" onClick={async () => {
          try { await api.clubDemoImport(); setMsg("Загружены демо-выгрузки: 90 игроков рынка и 19 игроков состава (вымышленные)"); setWarn([]); onDone(); }
          catch (e) { setMsg((e as Error).message); }
        }}>Демо-выгрузки</button>
      </div>
      {msg && <p className="small">{msg}</p>}
      {warn.map((w, i) => <p key={i} className="small warn-text">{w}</p>)}
    </section>
  );
}

// --- Скаутский отчёт ---
function Report({ id, onClose }: { id: number; onClose: () => void }) {
  const [rep, err] = useLoad(() => api.scoutReport(id), [id]);
  if (err) return <div className="card">{err}</div>;
  if (!rep) return <div className="card muted">Готовлю отчёт…</div>;
  const final = rep.sections[9];
  return (
    <section className="card report">
      <div className="row report__head">
        <h3>{rep.title}</h3>
        <span className={`verdict verdict--${VERDICT_CLASS[final.verdict]}`}>{final.verdict} · {final.verdict_ru}</span>
        <span className="pill">{final.grade} · {final.grade_ru}</span>
        <button className="btn btn--ghost" onClick={() => api.shortlistAdd(id)}>В шорт-лист</button>
        <button className="btn btn--ghost" onClick={onClose}>Закрыть</button>
      </div>
      <p className="muted small">{rep.disclaimer}</p>
      <div className="rsec rsec--wide conclusion-box">
        <h4>Единое заключение отделов</h4>
        <Conclusion id={id} />
      </div>
      <div className="report__grid">
        {rep.sections.map((s: any) => (
          <div key={s.n} className={`rsec ${s.n === 6 || s.n === 10 ? "rsec--wide" : ""}`}>
            <h4>{s.n}. {s.title}</h4>
            {s.rows && (
              <table className="tbl tbl--kv"><tbody>
                {s.rows.map((r: any[], i: number) => <tr key={i}><td>{r[0]}</td><td>{String(r[1])}</td></tr>)}
              </tbody></table>
            )}
            {s.items && <ul>{s.items.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>}
            {s.note && <p className="muted small">{s.note}</p>}
            {s.fit && (
              <>
                <p><b>Tactical Fit: {s.fit.score ?? "н/д"}/100</b> — профиль «{s.fit.profile_name}», достоверность {(s.fit.confidence * 100).toFixed(0)}%</p>
                <table className="tbl"><thead><tr><th>Фактор</th><th>Балл</th><th>Вес</th><th>Пояснение</th></tr></thead>
                  <tbody>{s.fit.components.map((c: any) => (
                    <tr key={c.name}><td>{c.name}</td><td>{c.score.toFixed(0)}</td><td>{(c.weight * 100).toFixed(0)}%</td><td className="small">{c.detail}</td></tr>
                  ))}</tbody></table>
                <details>
                  <summary>Атрибуты профиля и их вес</summary>
                  <table className="tbl"><thead><tr><th>Атрибут</th><th>Значение</th><th>Вес</th></tr></thead>
                    <tbody>{s.fit.attribute_rows.map((r: any) => (
                      <tr key={r.attr}><td>{r.name}</td><td>{r.value ?? <span className="muted">нет данных</span>}</td><td>{r.weight}</td></tr>
                    ))}</tbody></table>
                </details>
                {s.fit.notes.map((n: string, i: number) => <p key={i} className="muted small">{n}</p>)}
              </>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

const EXAMPLES = [
  "Молодой левый вингер до 21 года с хорошим дриблингом и ускорением, бюджет 15 миллионов",
  "Центральный защитник до 25 лет с хорошей игрой головой",
  "Свободные агенты",
  "Недооценённые опорные полузащитники",
];

export function ScoutSection() {
  const s = useCore();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<number | null>(null);
  const [sel, setSel] = useState<number[]>([]);
  const [cmp, setCmp] = useState<any>(null);
  const [imports, , reloadImports] = useLoad(() => (s.save ? api.clubImports() : Promise.resolve([])), [s.save]);
  if (!s.save) return <NeedSave />;
  const run = async (text: string) => {
    setQ(text); setBusy(true); setCmp(null); setSel([]);
    try { setRes(await api.scoutSearch(text)); setErr(null); } catch (e) { setErr((e as Error).message); setRes(null); }
    setBusy(false);
  };
  return (
    <div className="grid2">
      <ImportPanel onDone={reloadImports} />
      <section className="card">
        <h3>Загруженные выгрузки</h3>
        {imports && imports.length ? (
          <table className="tbl"><thead><tr><th>Файл</th><th>Что</th><th>Игроков</th><th>Когда</th></tr></thead>
            <tbody>{imports.slice(0, 6).map((i: any) => (
              <tr key={i.id}><td>{i.file}</td><td>{i.scope === "own" ? "состав" : "рынок"}</td><td>{i.rows}</td>
                <td>{new Date(i.imported_at * 1000).toLocaleString("ru-RU")}</td></tr>
            ))}</tbody></table>
        ) : <p className="muted">Пока ничего не загружено.</p>}
      </section>
      <section className="card span2">
        <h3>Поиск игроков</h3>
        <form className="ask" onSubmit={(e) => { e.preventDefault(); q.trim() && run(q.trim()); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Опишите, кого ищем, обычными словами…" />
          <button className="btn btn--primary" disabled={busy}>{busy ? "Ищу…" : "Найти"}</button>
        </form>
        <div className="chips">{EXAMPLES.map((x) => <button key={x} className="chip" onClick={() => run(x)}>{x}</button>)}</div>
        {err && <p className="warn-text">{err}</p>}
        {res && (
          <>
            <div className="understood">
              <b>Как я понял запрос</b> <span className="muted small">({res.parsed_by === "llm" ? "AI-аналитик" : "правила"}, в базе {res.pool} игроков)</span>
              <ul>{res.understood.map((u: string, i: number) => <li key={i}>{u}</li>)}</ul>
            </div>
            {res.hits.length ? (
              <table className="tbl">
                <thead><tr><th></th><th>Игрок</th><th>Возр.</th><th>Позиции</th><th>Клуб</th><th>Стоимость</th><th>Потенциал</th><th>Соответствие</th><th>Почему в списке</th><th></th></tr></thead>
                <tbody>{res.hits.map((h: any) => (
                  <tr key={h.id}>
                    <td><input type="checkbox" checked={sel.includes(h.id)} onChange={(e) => setSel(e.target.checked ? [...sel, h.id] : sel.filter((x) => x !== h.id))} /></td>
                    <td>{h.name}{h.free_agent && <span className="pill">свободный</span>}</td>
                    <td>{h.age ?? "—"}</td><td className="small">{h.positions.join(", ")}</td>
                    <td className="small">{h.club ?? "—"}</td><td>{h.value}</td><td><Stars v={h.potential_stars} /></td>
                    <td><FitBadge score={h.fit} conf={h.fit_confidence} /> <span className="muted small">{h.fit_profile}</span></td>
                    <td className="small">{h.reasons.join(", ")}</td>
                    <td><button className="btn btn--ghost" onClick={() => setReport(h.id)}>Отчёт</button></td>
                  </tr>
                ))}</tbody>
              </table>
            ) : <p className="muted">Никто не подошёл под все условия — ослабьте фильтры.</p>}
            <div className="row">
              <button className="btn" disabled={sel.length < 2} onClick={async () => setCmp(await api.scoutCompare(sel))}>
                Сравнить выбранных ({sel.length})
              </button>
              <span className="muted small">Соответствие — условная оценка помощника 0–100 (не рейтинг FM27); «~» — атрибуты известны диапазонами.</span>
            </div>
          </>
        )}
      </section>
      {cmp && (
        <section className="card span2">
          <h3>Сравнение{cmp.position ? ` · ${cmp.position}` : ""}</h3>
          {cmp.answer && <p className="answer__short">{cmp.answer}</p>}
          <table className="tbl">
            <thead><tr><th></th>{cmp.players.map((p: any) => <th key={p.id}>{p.name}</th>)}</tr></thead>
            <tbody>
              {[
                ["Возраст", (p: any) => p.age ?? "—"],
                ["Соответствие", (p: any) => <FitBadge score={p.fit} conf={p.confidence} />],
                ["Профиль", (p: any) => p.profile ?? "—"],
                ["Техника", (p: any) => p.groups.technical ?? "—"],
                ["Ментальные", (p: any) => p.groups.mental ?? "—"],
                ["Физика", (p: any) => p.groups.physical ?? "—"],
                ["Сильные", (p: any) => p.strengths.join(", ") || "—"],
                ["Слабые", (p: any) => p.weaknesses.join(", ") || "—"],
                ["Стоимость", (p: any) => p.value],
                ["Зарплата/нед.", (p: any) => p.wage],
                ["Потенциал", (p: any) => <Stars v={p.potential} />],
                ["Оценка", (p: any) => p.grade],
                ["Решение", (p: any) => <span className={`verdict verdict--${VERDICT_CLASS[p.verdict]}`}>{p.verdict}</span>],
              ].map(([label, fn]: any) => (
                <tr key={label}><td className="muted">{label}</td>{cmp.players.map((p: any) => <td key={p.id}>{fn(p)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {report !== null && <div className="span2"><Report id={report} onClose={() => setReport(null)} /></div>}
    </div>
  );
}

export function WonderkidsSection() {
  const s = useCore();
  const [data, err] = useLoad(() => (s.save ? api.wonderkids() : Promise.resolve(null)), [s.save]);
  const [report, setReport] = useState<number | null>(null);
  if (!s.save) return <NeedSave />;
  if (err) return <div className="card">{err}</div>;
  if (!data) return <div className="card muted">Загрузка…</div>;
  return (
    <div className="grid2">
      <section className="card span2">
        <h3>Поиск талантов до 21 года</h3>
        <p className="muted small">В базе {data.pool} молодых игроков. {data.notes.join(" ")}</p>
      </section>
      {data.categories.map((c: any) => (
        <section key={c.id} className="card">
          <h3>{c.title} <span className="muted small">{c.players.length}</span></h3>
          {c.players.length ? (
            <table className="tbl"><tbody>{c.players.slice(0, 6).map((p: any) => (
              <tr key={p.id}>
                <td>{p.name}</td><td>{p.age}</td><td className="small">{p.positions.join(", ")}</td>
                <td><FitBadge score={p.fit} /></td><td className="small muted">{p.why.join("; ")}</td>
                <td><button className="btn btn--ghost" onClick={() => setReport(p.id)}>Отчёт</button></td>
              </tr>
            ))}</tbody></table>
          ) : <p className="muted small">Никого в этой категории.</p>}
        </section>
      ))}
      {report !== null && <div className="span2"><Report id={report} onClose={() => setReport(null)} /></div>}
    </div>
  );
}

function SlotCard({ s }: { s: any }) {
  const line = (r: any, label: string) =>
    r ? (
      <div className="slot__row"><span className="muted small">{label}</span><span>{r.name}{r.age !== null ? `, ${r.age}` : ""}</span><FitBadge score={r.fit} conf={r.confidence} /></div>
    ) : (
      <div className="slot__row"><span className="muted small">{label}</span><span className="muted">—</span></div>
    );
  return (
    <div className={`slot slot--${s.need}`}>
      <div className="slot__head"><b>{s.label}</b><span className="small">{s.name}</span><span className={`need need--${s.need}`}>{s.need_ru}</span></div>
      {s.starters.map((r: any, i: number) => <div key={i}>{line(r, s.count > 1 ? `основной ${i + 1}` : "основной")}</div>)}
      {s.starters.length === 0 && line(null, "основной")}
      {line(s.second, "второй")}
      {line(s.backup, "запасной")}
      {s.youth && line(s.youth, "молодой")}
      {s.reasons.length > 0 && <p className="small warn-text">{s.reasons.join("; ")}</p>}
    </div>
  );
}

export function SquadSection() {
  const s = useCore();
  const [plan, err, reload] = useLoad(() => (s.save ? api.squadPlan() : Promise.resolve(null)), [s.save]);
  if (!s.save) return <NeedSave />;
  if (err) return (
    <div className="grid2"><ImportPanel onDone={reload} /><section className="card"><p>{err}</p></section></div>
  );
  if (!plan) return <div className="card muted">Загрузка…</div>;
  return (
    <div className="grid2">
      <section className="card span2">
        <h3>Приоритеты трансферного окна · схема {plan.formation}</h3>
        {plan.priorities.length ? <ol>{plan.priorities.map((t: string, i: number) => <li key={i}>{t}</li>)}</ol>
          : <p>Явных дыр в составе нет.</p>}
        <p className="muted small">{plan.disclaimer}. Схема и стиль берутся из раздела «ДНК клуба».</p>
      </section>
      <section className="card span2">
        <h3>Карта состава</h3>
        <div className="slots">{plan.slots.map((sl: any) => <SlotCard key={sl.code} s={sl} />)}</div>
      </section>
      <section className="card">
        <h3>Возрастная структура</h3>
        <table className="tbl"><tbody>
          {["до 21", "22–25", "26–29", "30+"].map((k) => <tr key={k}><td>{k}</td><td>{plan.age_structure[k] ?? 0}</td></tr>)}
        </tbody></table>
        <p className="muted small">Всего в составе: {plan.squad_size}</p>
      </section>
      <section className="card">
        <h3>Решения по игрокам</h3>
        {plan.player_verdicts.length ? (
          <table className="tbl"><tbody>{plan.player_verdicts.map((v: any) => (
            <tr key={v.id}><td>{v.name}</td><td>{v.age}</td>
              <td><span className={`verdict verdict--${VERDICT_CLASS[v.verdict]}`}>{v.verdict_ru}</span></td>
              <td className="small">{v.why}</td></tr>
          ))}</tbody></table>
        ) : <p className="muted">Всех стоит оставить.</p>}
      </section>
    </div>
  );
}

export function DnaSection() {
  const s = useCore();
  const [dna, err, reload] = useLoad(() => (s.save ? api.dna() : Promise.resolve(null)), [s.save]);
  const [form, setForm] = useState<any>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (dna) setForm(dna); }, [dna]);
  if (!s.save) return <NeedSave />;
  if (err) return <div className="card">{err}</div>;
  if (!form) return <div className="card muted">Загрузка…</div>;
  const set = (k: string, v: any) => { setForm({ ...form, [k]: v }); setSaved(false); };
  const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));
  return (
    <section className="card dna">
      <h3>ДНК клуба — философия, которую учитывают все отделы</h3>
      <div className="dna__grid">
        <label>Основная схема
          <select value={form.formation} onChange={(e) => set("formation", e.target.value)}>
            {FORMATIONS.map((f) => <option key={f}>{f}</option>)}
          </select>
        </label>
        <label>Трансферный бюджет, млн
          <input defaultValue={form.transfer_budget ? form.transfer_budget / 1e6 : ""} onChange={(e) => set("transfer_budget", num(e.target.value) === null ? null : num(e.target.value)! * 1e6)} />
        </label>
        <label>Лимит зарплаты игрока в неделю, тыс.
          <input defaultValue={form.wage_budget_week ? form.wage_budget_week / 1e3 : ""} onChange={(e) => set("wage_budget_week", num(e.target.value) === null ? null : num(e.target.value)! * 1e3)} />
        </label>
        <label>Максимальный возраст при покупке
          <input defaultValue={form.max_signing_age ?? ""} onChange={(e) => set("max_signing_age", num(e.target.value))} />
        </label>
        <label>Текущая дата в сейве (для контрактов)
          <input type="date" value={form.game_date ?? ""} onChange={(e) => set("game_date", e.target.value || null)} />
        </label>
        <label>Молодёжная политика
          <input value={form.youth_policy ?? ""} onChange={(e) => set("youth_policy", e.target.value || null)} placeholder="Например: 2 воспитанника в заявке" />
        </label>
      </div>
      <h4>Стиль игры</h4>
      <div className="chips">
        {Object.entries(STYLES).map(([k, label]) => (
          <label key={k} className={`chip ${form.style.includes(k) ? "chip--on" : ""}`}>
            <input type="checkbox" hidden checked={form.style.includes(k)}
              onChange={(e) => set("style", e.target.checked ? [...form.style, k] : form.style.filter((x: string) => x !== k))} />
            {label}
          </label>
        ))}
      </div>
      <p className="muted small">Стиль меняет веса атрибутов в Tactical Fit: например, «высокая линия» повышает важность скорости центральных защитников.</p>
      <div className="row">
        <button className="btn btn--primary" onClick={async () => { await api.setDna(form); setSaved(true); reload(); }}>Сохранить</button>
        {saved && <span className="muted small">Сохранено</span>}
      </div>
    </section>
  );
}
