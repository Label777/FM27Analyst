import { useEffect } from "react";
import { them, us } from "./lib/ru";
import { actions, bridgeActions, connect, latest, setVoice, useCore } from "./lib/store";
import { togglePanel } from "./lib/windows";

// Компактный виджет поверх игры: всё управление — кнопками.
// Перетаскивается за верхнюю строку.
export default function Compact() {
  const s = useCore();
  useEffect(() => {
    connect();
    document.body.classList.add("compact-body");
  }, []);
  const t = latest(s);
  const rec = [...s.recs].reverse().find((r) => r.status === "new");
  const alert = t?.signals.find((x) => x.severity !== "info");
  const level = t?.signals.some((x) => x.severity === "critical") ? "critical" : alert ? "warning" : "ok";

  return (
    <div className="compact">
      <div className="compact__head" data-tauri-drag-region title="Перетащите, чтобы передвинуть">
        <span className={`led ${s.connected ? "led--on" : ""}`} />
        {t ? (
          <b data-tauri-drag-region>{t.snapshot.minute}' · {t.snapshot.home_goals}:{t.snapshot.away_goals}</b>
        ) : (
          <b data-tauri-drag-region>{s.connected ? "Ждём матч" : "Ядро не запущено"}</b>
        )}
        <span className={`led ${s.bridge?.online ? "led--on" : ""}`} title={s.bridge?.online ? "FM27 на связи" : "Игра не на связи"} />
        <span className={`compact__lvl compact__lvl--${level}`} />
      </div>
      {t && (
        <div className="compact__line">
          xG {us(t.snapshot).stats.xg?.toFixed(2) ?? "—"} – {them(t.snapshot).stats.xg?.toFixed(2) ?? "—"}
          {us(t.snapshot).stats.possession !== null && ` · владение ${us(t.snapshot).stats.possession?.toFixed(0)}%`}
        </div>
      )}
      {alert && <div className="compact__line compact__alert" title={alert.title}>{alert.title}</div>}
      {rec && (() => {
        const text = `Совет (${rec.minute}'): ${rec.actions[0].text.split(":")[0].split(". Почему")[0]}`;
        return <div className="compact__line compact__rec" title={rec.actions[0].text}>{text}</div>;
      })()}
      {s.bridgeNote && <div className="compact__line compact__muted" title={s.bridgeNote}>Игра: {s.bridgeNote}</div>}
      {s.capture && !s.capture.ok && <div className="compact__line compact__muted" title={s.capture.message}>{s.capture.message}</div>}
      <div className="compact__btns">
        <button className="cbtn cbtn--primary" onClick={() => actions.analyze()} title="Снять текущий экран FM27 и разобрать его">
          Анализ экрана
        </button>
        {s.bridge?.online && (
          <button className="cbtn" onClick={() => bridgeActions.request("grab_table")} title="Забрать таблицу с экрана игры (состав, поиск, шорт-лист)">Таблицу</button>
        )}
        <button className="cbtn" onClick={() => togglePanel()} title="Открыть или скрыть расширенную панель">Панель</button>
        <button className={`cbtn ${s.voice ? "cbtn--on" : ""}`} onClick={() => setVoice(!s.voice)} title="Озвучивать советы">
          {s.voice ? "Голос вкл" : "Голос"}
        </button>
      </div>
    </div>
  );
}
