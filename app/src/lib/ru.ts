// Подписи интерфейса на русском
import type { Fatigue, Severity, Snapshot, TeamState } from "./types";

export const FATIGUE: Record<Fatigue, string> = {
  fresh: "свежий",
  ok: "в норме",
  tired: "устал",
  exhausted: "сильно устал",
  unknown: "—",
};

export const SEVERITY: Record<Severity, string> = {
  info: "инфо",
  warning: "внимание",
  critical: "критично",
};

export const CONFIDENCE = { low: "низкая", medium: "средняя", high: "высокая" } as const;

export const ACTION_KIND = {
  tactical_tweak: "Тактическая правка",
  role: "Роль",
  instruction: "Инструкция",
  substitution: "Замена",
  shout: "Указание",
  other: "Действие",
} as const;

export const SECTIONS = [
  { id: "game", label: "Связь с игрой", group: "Игра" },
  { id: "live", label: "Матч LIVE", group: "Матч" },
  { id: "tactics", label: "Тактика", group: "Матч" },
  { id: "players", label: "Игроки", group: "Матч" },
  { id: "opponent", label: "Соперник", group: "Матч" },
  { id: "subs", label: "Замены", group: "Матч" },
  { id: "home", label: "Главное меню", group: "Клуб" },
  { id: "scout", label: "Главный скаут", group: "Клуб" },
  { id: "wonderkids", label: "Таланты", group: "Клуб" },
  { id: "director", label: "Спортивный директор", group: "Клуб" },
  { id: "squad", label: "Состав", group: "Клуб" },
  { id: "youth", label: "Молодёжь", group: "Клуб" },
  { id: "finance", label: "Финансы", group: "Клуб" },
  { id: "recon", label: "Разведка соперника", group: "Клуб" },
  { id: "season", label: "Сезон", group: "Клуб" },
  { id: "dna", label: "ДНК клуба", group: "Клуб" },
  { id: "history", label: "История", group: "Общее" },
  { id: "chat", label: "AI-чат", group: "Общее" },
] as const;

export const STYLES: Record<string, string> = {
  high_press: "Высокий прессинг",
  high_line: "Высокая линия обороны",
  high_fullbacks: "Высокие крайние защитники",
  possession: "Контроль мяча",
  counter: "Контратаки",
  low_block: "Низкий блок",
};
export const FORMATIONS = ["4-2-3-1", "4-3-3", "4-4-2", "4-1-4-1", "3-5-2", "3-4-3", "3-2-4-1"];
export const VERDICT_CLASS: Record<string, string> = {
  BUY: "good", WATCH: "warn", AVOID: "crit", SELL: "crit", LOAN: "warn", KEEP: "good",
};
export type SectionId = (typeof SECTIONS)[number]["id"];

export const us = (s: Snapshot): TeamState => (s.our_side === "home" ? s.home : s.away);
export const them = (s: Snapshot): TeamState => (s.our_side === "home" ? s.away : s.home);

export const ATTR: Record<string, string> = {
  acceleration: "Ускорение", dribbling: "Дриблинг", work_rate: "Работоспособность", pace: "Скорость",
  crossing: "Навес", stamina: "Выносливость", tackling: "Отбор", positioning: "Выбор позиции",
  passing: "Пас", decisions: "Решения", vision: "Видение поля", anticipation: "Предвидение",
  marking: "Опека", heading: "Игра головой", finishing: "Завершение", off_the_ball: "Игра без мяча",
  composure: "Хладнокровие", flair: "Креативность",
};

export const fmt =(v: number | null | undefined, digits = 0, suffix = "") =>
  v === null || v === undefined ? "—" : v.toFixed(digits) + suffix;
