// Состояние приложения: одно WebSocket-подключение к ядру на окно.
import { useSyncExternalStore } from "react";
import { WS_URL, api } from "./api";
import type { Answer, BridgeStatus, CaptureResult, Health, Recommendation, Tick } from "./types";

export interface CoreState {
  connected: boolean;
  health: Health | null;
  save: { save_id: string; club: string; save_name: string } | null;
  match: { match_id: number; opponent: string; our_side: string } | null;
  ticks: Tick[];
  recs: Recommendation[];
  review: Recommendation[];
  answers: Answer[];
  capture: CaptureResult | null;
  voice: boolean;
  error: string | null;
  bridge: BridgeStatus | null;
  bridgeNote: string | null;
}

let state: CoreState = {
  connected: false,
  health: null,
  save: null,
  match: null,
  ticks: [],
  recs: [],
  review: [],
  answers: [],
  capture: null,
  voice: false,
  error: null,
  bridge: null,
  bridgeNote: null,
};

const listeners = new Set<() => void>();
function set(patch: Partial<CoreState>) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

export function useCore(): CoreState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
  );
}

export const latest = (s: CoreState): Tick | null => (s.ticks.length ? s.ticks[s.ticks.length - 1] : null);

// --- голос (временный: синтез речи браузера; полноценный голос — этап 6) ---
function speak(text: string) {
  if (!state.voice || !("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "ru-RU";
  u.rate = 1.05;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

/** Озвучить ответ, если включён голос. */
export const say = (text: string) => speak(text);

export function setVoice(on: boolean) {
  set({ voice: on });
  if (!on && "speechSynthesis" in window) window.speechSynthesis.cancel();
}

// --- подключение ---
let ws: WebSocket | null = null;
let retry = 0;

function handle(type: string, data: any) {
  switch (type) {
    case "hello":
      set({ health: data, connected: true, error: null });
      break;
    case "save":
      set({ save: data, match: null, ticks: [], recs: [], review: [], answers: [] });
      break;
    case "match":
      set({ match: data, ticks: [], recs: [], review: [] });
      break;
    case "tick": {
      const t = data as Tick;
      const ticks = [...state.ticks.filter((x) => x.snapshot.minute < t.snapshot.minute), t];
      const recs = [...state.recs, ...t.recommendations];
      set({ ticks, recs });
      if (t.recommendations.length) {
        const r = t.recommendations[0];
        speak(`${r.minute}-я минута. ${r.problem}. ${r.actions[0].text.split(". Почему")[0]}`);
      }
      break;
    }
    case "answer":
      set({ answers: [data as Answer, ...state.answers].slice(0, 30) });
      speak((data as Answer).short);
      break;
    case "review":
      set({ review: data as Recommendation[] });
      break;
    case "feedback":
      set({
        recs: state.recs.map((r) => (r.id === String(data.id) ? { ...r, status: data.status } : r)),
      });
      break;
    case "capture":
      set({ capture: data as CaptureResult });
      break;
    case "bridge":
      set({ bridge: data as BridgeStatus });
      break;
    case "bridge_screen":
      if (state.bridge) set({ bridge: { ...state.bridge, last_screen: data, online: true } });
      break;
    case "bridge_result":
      set({ bridgeNote: data.message });
      break;
  }
}

export function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    retry = 0;
    set({ connected: true });
    refreshBridge();
  };
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      handle(msg.type, msg.data);
    } catch {
      /* игнорируем битые сообщения */
    }
  };
  ws.onclose = () => {
    set({ connected: false });
    retry = Math.min(retry + 1, 6);
    setTimeout(connect, 500 * 2 ** retry);
  };
  ws.onerror = () => ws?.close();
}

// --- мост с игрой ---
export async function refreshBridge() {
  try {
    set({ bridge: await api.bridgeStatus() });
  } catch {
    /* ядро ещё не готово */
  }
}

// Плагин опрашивает ядро раз в секунду, а «отвалился» ядро видит только по тишине — переспрашиваем статус.
setInterval(() => {
  if (state.connected) refreshBridge();
}, 5000);

export const bridgeActions = {
  request: async (type: "grab_table" | "screen" | "tables" | "explore") => {
    set({ bridgeNote: null });
    return guard(api.bridgeRequest(type));
  },
  auto: (on: boolean, sec: number) => guard(api.bridgeAuto(on, sec)).then((b) => b && set({ bridge: b })),
  clearNote: () => set({ bridgeNote: null }),
};

// --- действия ---
async function guard<T>(p: Promise<T>): Promise<T | null> {
  try {
    const r = await p;
    set({ error: null });
    return r;
  } catch (e) {
    set({ error: (e as Error).message });
    return null;
  }
}

export const actions = {
  ask: (q: string) => guard(api.ask(q)),
  analyze: () => guard(api.analyze()),
  review: () => guard(api.review()),
  feedback: (id: string, status: "accepted" | "rejected") => guard(api.feedback(id, status)),
  openSave: (club: string, name: string) => guard(api.openSave(club, name)),
  startMatch: (opp: string, side: "home" | "away") => guard(api.startMatch(opp, side)),
  demo: () => guard(api.demoStart(2)),
  demoStop: () => guard(api.demoStop()),
  clearError: () => set({ error: null }),
};
