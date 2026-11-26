// Связь с игрой: плагин FM27 Analyst Bridge читает интерфейс FM27 и отдаёт данные ядру.
// Мост только читает экран игры — ничего в FM27 не нажимает и не меняет.
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { bridgeActions, refreshBridge, useCore } from "../lib/store";

const SCOPE_RU: Record<string, string> = { own: "мой состав", market: "рынок", opp: "соперник" };

function ago(ts: number | null | undefined): string {
  if (!ts) return "—";
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 5) return "только что";
  if (s < 60) return `${s} с назад`;
  if (s < 3600) return `${Math.round(s / 60)} мин назад`;
  return new Date(ts * 1000).toLocaleTimeString("ru-RU");
}

function plural(n: number, one: string, few: string, many: string) {
  const a = n % 10, b = n % 100;
  return `${n} ${a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many}`;
}

const ruDate = (iso: string | null | undefined) =>
  iso ? new Date(iso + "T12:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" }) : null;

export function GameSection() {
  const s = useCore();
  const b = s.bridge;
  const [interval, setIntervalSec] = useState(3);
  const [opp, setOpp] = useState("");
  const [replace, setReplace] = useState<boolean | null>(null);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [screen, setScreen] = useState<any>(null);
  const [showTexts, setShowTexts] = useState(false);

  const [plugin, setPlugin] = useState<any>(null);
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    refreshBridge();
    const load = () => api.appInfo().then((i) => { setVersion(i.version); setPlugin(i.plugin); }).catch(() => {});
    load();
    const t = setTimeout(load, 3000); // установка плагина идёт в фоне при старте ядра
    return () => clearTimeout(t);
  }, []);
  const reinstall = async () => setPlugin(await api.pluginInstall().catch(() => plugin));
  const t = b?.last_table;
  useEffect(() => { setResult(null); setErr(null); setReplace(null); }, [t?.id]);

  const doImport = async (scope: "own" | "market" | "opp") => {
    setErr(null);
    try {
      setResult(await api.bridgeImport(scope, scope === "opp" ? opp : undefined, replace ?? undefined));
      refreshBridge();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const loadTexts = async () => {
    setShowTexts(!showTexts);
    if (!showTexts) setScreen(await api.bridgeScreen().catch(() => null));
  };

  const online = !!b?.online;
  return (
    <div className="grid2">
      <section className="card span2">
        <h3>Связь с игрой</h3>
        <div className="row">
          <span className={`led ${online ? "led--on" : ""}`} />
          <b>{online ? "FM27 на связи" : "Игра не на связи"}</b>
          {b?.plugin && <span className="muted small">плагин {b.plugin.plugin_version} · игра {b.plugin.game_version}</span>}
          {b?.game_date && (
            <span className="pill" title={`Найдено на экране: «${b.game_date_text}»`}>Дата в игре: {ruDate(b.game_date)}</span>
          )}
        </div>
        {!online && (
          <div className="muted small" style={{ marginTop: 10 }}>
            <p>Помощник видит игру через плагин <b>FM27 Analyst Bridge</b> (работает через BepInEx) и сам ставит его в FM27 при запуске.
              Плагин только читает то, что видно на экране, — в игре он ничего не нажимает и не меняет.</p>
            <p>Запустите игру — статус сменится сам. {b?.last_seen ? `Последний сигнал: ${ago(b.last_seen)}.` : ""}</p>
          </div>
        )}
        {plugin && (
          <div className="small" style={{ marginTop: 8 }}>
            {plugin.games?.map((g: any, i: number) => (
              <p key={i} style={{ margin: "2px 0", color: g.plugin === "outdated_locked" || g.plugin === "no_bepinex" || g.plugin === "error" ? "var(--warn)" : undefined }}>
                Плагин в «{g.path.split(/[\\/]/).pop()}»: {g.message}
              </p>
            ))}
            {plugin.note && <p className="muted" style={{ margin: "2px 0" }}>{plugin.note}</p>}
            <button className="btn btn--xs btn--ghost" onClick={reinstall}>Проверить плагин ещё раз</button>
            {version && <span className="muted"> · FM27 Analyst {version}</span>}
          </div>
        )}
        {online && (
          <>
            <p className="muted small">Откройте в игре нужный экран (состав, поиск игроков, шорт-лист, состав соперника) и нажмите кнопку.</p>
            <div className="row">
              <button className="btn btn--primary" onClick={() => bridgeActions.request("grab_table")}
                title="Прочитать таблицу на экране игры целиком (список прокручивается и возвращается на место)">
                Забрать таблицу с экрана
              </button>
              <button className="btn" onClick={() => bridgeActions.request("tables")}>Какие таблицы на экране</button>
              <button className="btn" onClick={() => bridgeActions.request("screen")} title="Все тексты на экране игры — для разбора матча и настройки">
                Снять тексты экрана
              </button>
              <button className="btn btn--ghost" onClick={() => bridgeActions.request("explore")}
                title="Для разработки: выгрузить справочник типов данных движка FM27 (что можно читать из базы)">
                Разведка движка
              </button>
            </div>
            {s.bridgeNote && <div className="toast toast--info" onClick={bridgeActions.clearNote}>Игра: {s.bridgeNote}</div>}
            {b && b.tables_on_screen.length > 0 && (
              <p className="muted small">На экране: {b.tables_on_screen.map((x) => `${x.screen} (${x.rows ?? "?"} стр., ${x.columns} кол.)`).join("; ")}.
                Забирается самая большая таблица на экране.</p>
            )}
          </>
        )}
      </section>

      <section className="card">
        <h3>Матч в реальном времени</h3>
        <p className="muted small">Плагин сам присылает тексты экрана, когда они меняются: счёт, минута, статистика. Для разбора матча без скриншотов.</p>
        <div className="row">
          <button className={`btn ${b?.auto_screen ? "btn--primary" : ""}`} disabled={!online}
            onClick={() => bridgeActions.auto(!b?.auto_screen, interval)}>
            {b?.auto_screen ? "Авто-снимки: вкл" : "Авто-снимки: выкл"}
          </button>
          <label className="small muted">раз в
            <select value={interval} onChange={(e) => { const v = Number(e.target.value); setIntervalSec(v); if (b?.auto_screen) bridgeActions.auto(true, v); }}>
              {[2, 3, 5, 10].map((v) => <option key={v} value={v}>{v} с</option>)}
            </select>
          </label>
        </div>
        {b?.last_screen && (
          <p className="small">
            Последний снимок: <b>{b.last_screen.screen || "экран"}</b>, {plural(b.last_screen.text_count, "текст", "текста", "текстов")}, {ago(b.last_screen.received_at)}
            {b.last_screen.truncated && <span className="muted"> (обрезано)</span>}
            {" "}<button className="btn btn--xs btn--ghost" onClick={loadTexts}>{showTexts ? "скрыть" : "показать тексты"}</button>
          </p>
        )}
        <p className="muted small">Распознавание счёта и статистики по этим текстам включу после первых снимков с вашего матча — названия элементов экрана нужно сверить с настоящей игрой.</p>
      </section>

      <section className="card">
        <h3>Последняя таблица из игры</h3>
        {!t && <p className="muted">Пока ничего не забрано.</p>}
        {t && (
          <>
            <p>
              <b>{t.screen || "Таблица"}</b>: {plural(t.row_count, "строка", "строки", "строк")}
              {t.expected_rows && t.expected_rows !== t.row_count ? ` из ${t.expected_rows}` : ""},{" "}
              {plural(t.headers.length, "колонка", "колонки", "колонок")} · {ago(t.received_at)}
              {t.game_date ? <> · на {ruDate(t.game_date)}</> : <span className="muted"> · дата в игре не найдена</span>}
            </p>
            {t.notes.map((n, i) => <p key={i} className="small" style={{ color: "var(--warn)" }}>{n}</p>)}
            {t.missing_rows > 0 && <p className="small" style={{ color: "var(--warn)" }}>Не прочитано строк: {t.missing_rows}</p>}
            {t.imported ? (
              <p className="small" style={{ color: "var(--good)" }}>
                Импортировано как «{SCOPE_RU[t.imported.scope.split(":")[0]] ?? t.imported.scope}»: новых {t.imported.added}, обновлено {t.imported.updated}.
              </p>
            ) : (
              <>
                <h4>Чья это таблица?</h4>
                {t.suggested_scope && <p className="muted small">По названию экрана похоже на «{SCOPE_RU[t.suggested_scope]}» — проверьте.</p>}
                <div className="row">
                  <button className={`btn ${t.suggested_scope === "own" ? "btn--primary" : ""}`} onClick={() => doImport("own")}>Мой состав</button>
                  <button className={`btn ${t.suggested_scope === "market" ? "btn--primary" : ""}`} onClick={() => doImport("market")}>Рынок / поиск</button>
                </div>
                <div className="row" style={{ marginTop: 8 }}>
                  <input className="inp" value={opp} onChange={(e) => setOpp(e.target.value)} placeholder="Название соперника" />
                  <button className={`btn ${opp.trim() ? "" : "btn--disabled"}`} onClick={() => doImport("opp")}>Состав соперника</button>
                </div>
                <label className="small muted" style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "flex-start" }}>
                  <input type="checkbox" checked={replace ?? false} onChange={(e) => setReplace(e.target.checked)} />
                  заменить прежние данные этого раздела (для своего состава и соперника — по умолчанию)
                </label>
              </>
            )}
            {err && <div className="toast" onClick={() => setErr(null)}>{err}</div>}
            {result && (
              <p className="small">
                Игроков: {result.rows}, распознано колонок: {Object.keys(result.mapped).length} из {t.headers.length}.
                {result.unmapped?.length > 0 && <span className="muted"> Не распознаны: {result.unmapped.join(", ")}.</span>}
                {result.notes?.map((n: string, i: number) => <span key={i} className="muted"> {n}</span>)}
              </p>
            )}
            {t.preview.length > 0 && (
              <div style={{ overflowX: "auto" }}>
                <table className="tbl small">
                  <thead><tr>{t.headers.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
                  <tbody>{t.preview.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>

      {showTexts && screen && (
        <section className="card span2">
          <h3>Тексты экрана «{screen.screen || "—"}»</h3>
          <p className="muted small">Сверху вниз, как на экране. Это сырые данные: из них будет собираться разбор матча.</p>
          <div style={{ maxHeight: 360, overflow: "auto" }}>
            <table className="tbl small">
              <tbody>{screen.texts.slice(0, 300).map((x: any, i: number) => (
                <tr key={i}><td>{x.t}</td><td className="muted">{x.path.split(" > ").slice(-2).join(" › ")}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
