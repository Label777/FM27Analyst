// HTTP-клиент локального ядра (Python, 127.0.0.1:8727)

// Если интерфейс открыт прямо из ядра (http://127.0.0.1:8727 в браузере) — обращаемся к тому же адресу.
const SERVED_BY_CORE = typeof location !== "undefined" && location.port === "8727";
export const CORE_URL =
  (import.meta.env.VITE_CORE_URL as string | undefined) ?? (SERVED_BY_CORE ? location.origin : "http://127.0.0.1:8727");
export const WS_URL = CORE_URL.replace(/^http/, "ws") + "/ws";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(CORE_URL + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : `Ошибка ${res.status}`;
    throw new Error(detail);
  }
  return body as T;
}

const post = <T>(path: string, data?: unknown) =>
  call<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const api = {
  health: () => call("/api/health"),
  saves: () => call<{ save_id: string; club: string; save_name: string }[]>("/api/saves"),
  openSave: (club: string, save_name: string) => post("/api/saves", { club, save_name }),
  startMatch: (opponent: string, our_side: "home" | "away") => post("/api/matches", { opponent, our_side }),
  matches: () => call<import("./types").MatchRow[]>("/api/matches"),
  snapshot: (snap: unknown) => post("/api/snapshots", snap),
  ask: (question: string) => post<import("./types").Answer>("/api/ask", { question }),
  review: () => post<{ recommendations: import("./types").Recommendation[] }>("/api/review"),
  history: () => call<import("./types").HistoryItem[]>("/api/recommendations"),
  feedback: (id: string, status: "accepted" | "rejected") =>
    post(`/api/recommendations/${id}/feedback`, { status }),
  analyze: () => post<import("./types").CaptureResult>("/api/capture/analyze"),
  demoStart: (seconds_per_step = 2) => post("/api/demo/start", { seconds_per_step }),
  demoStop: () => post("/api/demo/stop"),
  // --- отделы клуба ---
  clubImport: (filename: string, content: string, scope: "own" | "market", replace = false) =>
    post<any>("/api/club/import", { filename, content, scope, replace }),
  clubDemoImport: () => post<any>("/api/club/demo-import"),
  clubImports: () => call<any[]>("/api/club/imports"),
  clubPlayers: (scope: "own" | "market") => call<any[]>(`/api/club/players?scope=${scope}`),
  dna: () => call<any>("/api/club/dna"),
  setDna: (dna: any) => call<any>("/api/club/dna", { method: "PUT", body: JSON.stringify(dna) }),
  scoutSearch: (query: string) => post<any>("/api/scout/search", { query }),
  scoutReport: (id: number) => call<any>(`/api/scout/report/${id}`),
  scoutCompare: (ids: number[]) => post<any>("/api/scout/compare", { ids }),
  wonderkids: () => call<any>("/api/scout/wonderkids"),
  squadPlan: () => call<any>("/api/squad/plan"),
  shortlist: () => call<any[]>("/api/scout/shortlist"),
  shortlistAdd: (id: number) => post(`/api/scout/shortlist/${id}`),
  // --- отделы ---
  dashboard: () => call<any[]>("/api/department/dashboard"),
  deptAsk: (question: string) => post<any>("/api/department/ask", { question }),
  conclusion: (id: number) => call<any>(`/api/department/player/${id}`),
  window: (query: string) => post<any>("/api/director/window", { query }),
  deal: (id: number) => call<any>(`/api/director/deal/${id}`),
  finance: () => call<any>("/api/finance/report"),
  youth: () => call<any>("/api/youth/report"),
  oppList: () => call<any[]>("/api/opposition/list"),
  oppImport: (name: string, filename: string, content: string) => post<any>("/api/opposition/import", { name, filename, content }),
  oppReport: (scope: string) => call<any>(`/api/opposition/report?scope=${encodeURIComponent(scope)}`),
  season: () => call<any>("/api/season/report"),
  seasonDemo: () => post<any>("/api/season/demo"),
  seasonResult: (r: any) => post<any>("/api/season/result", r),
  // --- мост с игрой (плагин FM27 Analyst Bridge) ---
  bridgeStatus: () => call<import("./types").BridgeStatus>("/api/bridge/status"),
  bridgeRequest: (type: "grab_table" | "screen" | "tables", table_index?: number) =>
    post<{ id: string; status: string }>("/api/bridge/request", { type, table_index }),
  bridgeAuto: (enabled: boolean, interval_sec = 3) => post<import("./types").BridgeStatus>("/api/bridge/auto", { enabled, interval_sec }),
  bridgeImport: (scope: "own" | "market" | "opp", opponent?: string, replace?: boolean) =>
    post<any>("/api/bridge/import", { scope, opponent, replace }),
  bridgeTable: () => call<any>("/api/bridge/table/last"),
  bridgeScreen: () => call<any>("/api/bridge/screen/last"),
};
