import { useEffect, useState } from "react";
import { SetupPanel } from "./components";
import { hidePanel, isTauri } from "./lib/windows";
import { SECTIONS, type SectionId } from "./lib/ru";
import { actions, connect, latest, setVoice, useCore } from "./lib/store";
import {
  HistorySection, LiveSection, OpponentSection, PlayersSection, SubsSection, TacticsSection,
} from "./sections";
import { DnaSection, ScoutSection, SquadSection, WonderkidsSection } from "./sections/club";
import {
  DeptChatSection, DirectorSection, FinanceSection, HomeSection, ReconSection, SeasonSection, YouthSection,
} from "./sections/departments";
import { GameSection } from "./sections/game";

const VIEWS: Record<SectionId, () => JSX.Element> = {
  game: GameSection,
  live: LiveSection,
  tactics: TacticsSection,
  players: PlayersSection,
  opponent: OpponentSection,
  subs: SubsSection,
  home: HomeSection,
  scout: ScoutSection,
  wonderkids: WonderkidsSection,
  director: DirectorSection,
  squad: SquadSection,
  youth: YouthSection,
  finance: FinanceSection,
  recon: ReconSection,
  season: SeasonSection,
  dna: DnaSection,
  history: HistorySection,
  chat: DeptChatSection,
};

const MODE_LABEL = { quick: "Быстрый совет", live: "Live-аналитик", head_coach: "Главный тренер" };

export default function App() {
  const s = useCore();
  const [section, setSection] = useState<SectionId>("home");
  const [setup, setSetup] = useState(false);
  const [mode, setMode] = useState<keyof typeof MODE_LABEL>("live");

  useEffect(() => {
    connect();
    const nav = (e: Event) => setSection((e as CustomEvent).detail as SectionId);
    window.addEventListener("fm27-nav", nav);
    return () => window.removeEventListener("fm27-nav", nav);
  }, []);

  const pickMode = (m: keyof typeof MODE_LABEL) => {
    setMode(m);
    setSection(m === "quick" ? "chat" : m === "head_coach" ? "tactics" : "live");
  };

  const t = latest(s);
  const View = VIEWS[section];
  const newRecs = s.recs.filter((r) => r.status === "new").length;

  return (
    <div className="app">
      <header className="top">
        <div className="brand">FM27 Analyst</div>
        <div className="status">
          <span className={`led ${s.connected ? "led--on" : ""}`} />
          {s.connected ? "Ядро подключено" : "Ядро не запущено"}
          {t && <b> · {t.snapshot.minute}' {t.snapshot.home_goals}:{t.snapshot.away_goals}</b>}
          {s.health && (
            <span className="muted" title={s.health.llm ? "" : "Нет ANTHROPIC_API_KEY — советы по правилам"}>
              {" "}· AI: {s.health.llm ? "LLM" : "правила"}
            </span>
          )}
          {s.save && <span className="muted"> · {s.save.club} / {s.save.save_name}</span>}
          <span className="muted" role="button" style={{ cursor: "pointer" }} onClick={() => setSection("game")}
            title="Связь с FM27 через плагин FM27 Analyst Bridge">
            {" "}· <span className={`led ${s.bridge?.online ? "led--on" : ""}`} /> Игра
            {s.bridge?.game_date ? ` ${new Date(s.bridge.game_date + "T12:00:00").toLocaleDateString("ru-RU")}` : ""}
          </span>
        </div>
        <div className="seg seg--small">
          {(Object.keys(MODE_LABEL) as (keyof typeof MODE_LABEL)[]).map((m) => (
            <button key={m} className={mode === m ? "on" : ""} onClick={() => pickMode(m)}>{MODE_LABEL[m]}</button>
          ))}
        </div>
        <div className="row">
          <button className="btn btn--primary" onClick={() => actions.analyze()} title="Снять текущий экран FM27 и разобрать его">Анализ экрана</button>
          <button className={`btn ${s.voice ? "btn--primary" : ""}`} onClick={() => setVoice(!s.voice)} title="Озвучивать советы">
            {s.voice ? "Голос: вкл" : "Голос: выкл"}
          </button>
          <button className="btn btn--ghost" onClick={() => setSetup(true)}>Сейв и матч</button>
          {isTauri() && <button className="btn btn--ghost" onClick={() => hidePanel()} title="Скрыть панель, оставить виджет поверх игры">Свернуть в виджет</button>}
        </div>
      </header>
      <div className="body">
        <nav className="nav">
          {SECTIONS.map((x, i) => (
            <div key={x.id}>
              {(i === 0 || SECTIONS[i - 1].group !== x.group) && <div className="nav__group">{x.group}</div>}
              <button className={section === x.id ? "on" : ""} onClick={() => setSection(x.id)}>
                {x.label}
                {x.id === "live" && newRecs > 0 && <span className="badge">{newRecs}</span>}
              </button>
            </div>
          ))}
          <div className="nav__foot muted small">
            Управление — кнопками вверху и в виджете поверх игры
          </div>
        </nav>
        <main className="main">
          {s.error && (
            <div className="toast" onClick={actions.clearError}>{s.error}</div>
          )}
          {s.capture && (
            <div className={`toast ${s.capture.ok ? "toast--ok" : "toast--info"}`}>
              Снимок экрана: {s.capture.message}
            </div>
          )}
          <View />
        </main>
      </div>
      {setup && <SetupPanel onClose={() => setSetup(false)} />}
    </div>
  );
}
