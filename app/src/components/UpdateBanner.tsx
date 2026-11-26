// Баннер обновления: ядро сверяется с релизами GitHub, по кнопке скачивает и запускает установщик.
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useCore } from "../lib/store";

export function UpdateBanner() {
  const s = useCore();
  const [info, setInfo] = useState<{ latest: string | null; available: boolean; notes: string } | null>(null);
  const [state, setState] = useState<"idle" | "busy" | "started" | "error">("idle");
  const [msg, setMsg] = useState("");
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    if (!s.connected) return;
    api.updateCheck().then(setInfo).catch(() => setInfo(null));
  }, [s.connected]);

  if (!info?.available || hidden) return null;

  const install = async () => {
    setState("busy");
    try {
      const r = await api.updateInstall();
      setState("started");
      setMsg(`Устанавливаю версию ${r.version}: приложение закроется и откроется заново.`);
    } catch (e) {
      setState("error");
      setMsg((e as Error).message);
    }
  };

  return (
    <div className="toast toast--ok" style={{ cursor: "default" }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span>
          Доступна новая версия <b>{info.latest}</b>.
          {state !== "idle" && state !== "busy" && <span> {msg}</span>}
        </span>
        <span className="row">
          {state === "idle" && <button className="btn btn--primary" onClick={install}>Обновить</button>}
          {state === "busy" && <span className="muted">Скачиваю…</span>}
          {state === "error" && <button className="btn" onClick={install}>Повторить</button>}
          {state !== "started" && <button className="btn btn--ghost" onClick={() => setHidden(true)}>Позже</button>}
        </span>
      </div>
      {info.notes && state === "idle" && <div className="small muted" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{info.notes}</div>}
    </div>
  );
}
