// Управление окнами приложения. Горячих клавиш нет — всё через кнопки интерфейса.
import { invoke } from "@tauri-apps/api/core";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** Показать/скрыть расширенную панель. В браузере — открыть её во вкладке. */
export async function togglePanel(): Promise<void> {
  if (!isTauri()) {
    window.open("/", "fm27-main");
    return;
  }
  try {
    await invoke("toggle_main_window");
  } catch {
    /* окно недоступно */
  }
}

/** Свернуть панель обратно в компактный виджет (только в приложении). */
export async function hidePanel(): Promise<void> {
  if (!isTauri()) return;
  try {
    await invoke("hide_main_window");
  } catch {
    /* noop */
  }
}
