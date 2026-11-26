import { useState } from "react";
import { actions, useCore } from "../lib/store";
import { ACTION_KIND, CONFIDENCE, SEVERITY, fmt, them, us } from "../lib/ru";
import type { Fact, Recommendation, Signal, Snapshot, Tick } from "../lib/types";

// --- Совет: проблема → действия → эффект → риски ---
export function RecCard({ rec, facts, compact = false }: { rec: Recommendation; facts: Fact[]; compact?: boolean }) {
  const [open, setOpen] = useState(!compact);
  const byId = new Map(facts.map((f) => [f.id, f]));
  return (
    <article className={`rec rec--${rec.status}`}>
      <header className="rec__head">
        <span className="rec__min">{rec.minute}'</span>
        <span className="rec__title">{rec.problem}</span>
        <span className={`pill pill--conf-${rec.confidence}`}>уверенность {CONFIDENCE[rec.confidence]}</span>
      </header>
      <ol className="rec__actions">
        {rec.actions.map((a, i) => (
          <li key={i}>
            <span className="rec__kind">{ACTION_KIND[a.kind]}</span> {a.text}
          </li>
        ))}
      </ol>
      {open && (
        <div className="rec__body">
          <p><b>Ожидаемый эффект:</b> {rec.expected_effect}</p>
          <p><b>Риски:</b> {rec.risks}</p>
          <details>
            <summary>Основание — {rec.evidence_fact_ids.length} факт(а)</summary>
            <ul className="evidence">
              {rec.evidence_fact_ids.map((id) => (
                <li key={id}>{byId.get(id)?.text ?? id}</li>
              ))}
            </ul>
          </details>
          {rec.missing_data.length > 0 && (
            <p className="muted">Не хватает данных: {rec.missing_data.join("; ")}</p>
          )}
          <p className="muted small">Источник совета: {rec.generated_by === "llm" ? "AI-аналитик" : "правила"}</p>
        </div>
      )}
      <footer className="rec__foot">
        {rec.status === "new" && rec.id ? (
          <>
            <button className="btn btn--primary" onClick={() => actions.feedback(rec.id, "accepted")}>Принять</button>
            <button className="btn" onClick={() => actions.feedback(rec.id, "rejected")}>Отклонить</button>
          </>
        ) : (
          <span className="muted small">{rec.status === "accepted" ? "Принят" : rec.status === "rejected" ? "Отклонён" : ""}</span>
        )}
        {compact && (
          <button className="btn btn--ghost" onClick={() => setOpen(!open)}>{open ? "Свернуть" : "Подробнее"}</button>
        )}
      </footer>
    </article>
  );
}

export function SignalList({ signals }: { signals: Signal[] }) {
  const shown = signals.filter((s) => s.rule_id !== "tactic_working");
  const working = signals.find((s) => s.rule_id === "tactic_working");
  if (!shown.length && !working) return <p className="muted">Предупреждений нет.</p>;
  return (
    <ul className="signals">
      {working && (
        <li className="sig sig--good">
          <span className="dot" /> {working.title}
        </li>
      )}
      {shown.map((s, i) => (
        <li key={i} className={`sig sig--${s.severity}`}>
          <span className="dot" />
          <span>{s.title}</span>
          <span className="sig__sev">{SEVERITY[s.severity]}</span>
        </li>
      ))}
    </ul>
  );
}

export function Scoreboard({ snap }: { snap: Snapshot }) {
  return (
    <div className="score">
      <div className="score__team">{snap.home.name}</div>
      <div className="score__num">
        {snap.home_goals}:{snap.away_goals}
      </div>
      <div className="score__team score__team--away">{snap.away.name}</div>
      <div className="score__min">{snap.minute}'</div>
    </div>
  );
}

function Bar({ label, a, b, digits = 0, suffix = "" }: { label: string; a: number | null; b: number | null; digits?: number; suffix?: string }) {
  const total = (a ?? 0) + (b ?? 0);
  const pa = total > 0 && a !== null ? (a / total) * 100 : 50;
  return (
    <div className="bar">
      <span className="bar__v">{fmt(a, digits, suffix)}</span>
      <div className="bar__track">
        <div className="bar__us" style={{ width: `${pa}%` }} />
        <div className="bar__them" style={{ width: `${100 - pa}%` }} />
        <span className="bar__label">{label}</span>
      </div>
      <span className="bar__v bar__v--r">{fmt(b, digits, suffix)}</span>
    </div>
  );
}

export function StatBars({ snap }: { snap: Snapshot }) {
  const a = us(snap).stats;
  const b = them(snap).stats;
  return (
    <div className="bars">
      <div className="bars__legend">
        <span className="lg lg--us">Мы</span>
        <span className="lg lg--them">Соперник</span>
      </div>
      <Bar label="Владение" a={a.possession} b={b.possession} suffix="%" />
      <Bar label="xG" a={a.xg} b={b.xg} digits={2} />
      <Bar label="Удары" a={a.shots} b={b.shots} />
      <Bar label="В створ" a={a.shots_on_target} b={b.shots_on_target} />
      <Bar label="Точность передач" a={a.pass_accuracy} b={b.pass_accuracy} suffix="%" />
    </div>
  );
}

// --- xG по ходу матча: две ступенчатые линии ---
export function XgChart({ ticks }: { ticks: Tick[] }) {
  const pts = ticks
    .map((t) => ({ m: t.snapshot.minute, u: us(t.snapshot).stats.xg, t: them(t.snapshot).stats.xg }))
    .filter((p) => p.u !== null && p.t !== null) as { m: number; u: number; t: number }[];
  if (pts.length < 2) return <p className="muted">xG-график появится после второго снимка.</p>;
  const W = 520, H = 160, L = 34, R = 12, T = 12, B = 24;
  const maxM = Math.max(90, ...pts.map((p) => p.m));
  const maxX = Math.max(0.5, ...pts.map((p) => Math.max(p.u, p.t))) * 1.1;
  const x = (m: number) => L + (m / maxM) * (W - L - R);
  const y = (v: number) => T + (1 - v / maxX) * (H - T - B);
  const path = (k: "u" | "t") => pts.map((p, i) => `${i ? "L" : "M"}${x(p.m).toFixed(1)},${y(p[k]).toFixed(1)}`).join("");
  const ticksY = [0, maxX / 2, maxX].map((v) => +v.toFixed(1));
  const last = pts[pts.length - 1];
  return (
    <svg className="xg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="xG по ходу матча">
      {ticksY.map((v) => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid" />
          <text x={L - 6} y={y(v) + 4} textAnchor="end" className="axis">{v.toFixed(1)}</text>
        </g>
      ))}
      {[0, 45, 90].map((m) => (
        <text key={m} x={x(m)} y={H - 6} textAnchor="middle" className="axis">{m}'</text>
      ))}
      <line x1={x(45)} x2={x(45)} y1={T} y2={H - B} className="grid grid--dash" />
      <path d={path("t")} className="line line--them" />
      <path d={path("u")} className="line line--us" />
      <text x={x(last.m) + 4} y={y(last.u) - 4} className="lbl lbl--us">мы {last.u.toFixed(2)}</text>
      <text x={x(last.m) + 4} y={y(last.t) + 12} className="lbl lbl--them">соп. {last.t.toFixed(2)}</text>
    </svg>
  );
}

// --- Настройка: сейв, матч, демо ---
export function SetupPanel({ onClose }: { onClose: () => void }) {
  const s = useCore();
  const [club, setClub] = useState(s.save?.club ?? "");
  const [name, setName] = useState(s.save?.save_name ?? "");
  const [opp, setOpp] = useState("");
  const [side, setSide] = useState<"home" | "away">("home");
  return (
    <div className="modal" role="dialog" aria-label="Сейв и матч">
      <div className="modal__box">
        <h2>Сохранение и матч</h2>
        <p className="muted small">Данные каждого сохранения хранятся отдельно и не смешиваются.</p>
        <label>Клуб<input value={club} onChange={(e) => setClub(e.target.value)} placeholder="Например, Динамо Киев" /></label>
        <label>Название сейва<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Карьера 2026" /></label>
        <button className="btn btn--primary" disabled={!club || !name} onClick={() => actions.openSave(club, name)}>Открыть сохранение</button>
        <hr />
        <label>Соперник<input value={opp} onChange={(e) => setOpp(e.target.value)} placeholder="Название соперника" /></label>
        <div className="seg">
          <button className={side === "home" ? "on" : ""} onClick={() => setSide("home")}>Дома</button>
          <button className={side === "away" ? "on" : ""} onClick={() => setSide("away")}>В гостях</button>
        </div>
        <button className="btn btn--primary" disabled={!s.save || !opp} onClick={() => actions.startMatch(opp, side)}>Начать матч</button>
        <hr />
        <p className="muted small">Демо проигрывает сценарий из ТЗ: 0:1, владение 65%, моментов нет, вингер устаёт.</p>
        <div className="row">
          <button className="btn" onClick={() => { actions.demo(); onClose(); }}>Запустить демо-матч</button>
          <button className="btn btn--ghost" onClick={() => actions.demoStop()}>Остановить</button>
        </div>
        <button className="btn btn--ghost modal__close" onClick={onClose}>Закрыть</button>
      </div>
    </div>
  );
}
