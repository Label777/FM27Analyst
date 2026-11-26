// FM27 Analyst — оболочка Tauri.
// Два окна: "compact" (небольшой виджет поверх игры с кнопками «Анализ экрана»,
// «Панель», «Голос») и "main" (расширенная панель). Горячих клавиш нет:
// всё управление — кнопками интерфейса, поэтому клавиши игры и плагинов
// экспорта (F8/F9) остаются свободными.
// При запуске поднимается аналитическое ядро (Python) как дочерний процесс.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{AppHandle, Manager, RunEvent, WindowEvent};

struct Core(Mutex<Option<Child>>);

#[tauri::command]
fn toggle_main_window(app: AppHandle) -> Result<bool, String> {
    let main = app.get_webview_window("main").ok_or("окно main не найдено")?;
    let visible = main.is_visible().map_err(|e| e.to_string())?;
    if visible {
        main.hide().map_err(|e| e.to_string())?;
    } else {
        main.show().map_err(|e| e.to_string())?;
        main.unminimize().map_err(|e| e.to_string())?;
        main.set_focus().map_err(|e| e.to_string())?;
    }
    Ok(!visible)
}

#[tauri::command]
fn hide_main_window(app: AppHandle) -> Result<(), String> {
    let main = app.get_webview_window("main").ok_or("окно main не найдено")?;
    main.hide().map_err(|e| e.to_string())
}

/// Запуск ядра: FM27_CORE_CMD (для разработки) или fm27-core.exe рядом с приложением.
fn spawn_core() -> Option<Child> {
    let mut cmd = if let Ok(custom) = std::env::var("FM27_CORE_CMD") {
        let mut parts = custom.split_whitespace();
        let mut c = Command::new(parts.next()?);
        c.args(parts);
        c
    } else {
        let exe = std::env::current_exe().ok()?;
        let name = if cfg!(windows) { "fm27-core.exe" } else { "fm27-core" };
        let path = exe.parent()?.join(name);
        if !path.exists() {
            eprintln!("[fm27] ядро не найдено ({}), запустите его вручную", path.display());
            return None;
        }
        Command::new(path)
    };
    cmd.args(["--port", "8727"]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    match cmd.spawn() {
        Ok(child) => Some(child),
        Err(e) => {
            eprintln!("[fm27] не удалось запустить ядро: {e}");
            None
        }
    }
}

fn main() {
    let app = tauri::Builder::default()
        .manage(Core(Mutex::new(None)))
        .setup(|app| {
            let child = spawn_core();
            *app.state::<Core>().0.lock().unwrap() = child;
            Ok(())
        })
        .on_window_event(|window, event| {
            // Крестик на панели не закрывает её, а прячет: виджет поверх игры остаётся,
            // и кнопка «Панель» снова её откроет. Выход — закрыть виджет.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    api.prevent_close();
                    let _ = window.hide();
                } else if window.label() == "compact" {
                    window.app_handle().exit(0);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![toggle_main_window, hide_main_window])
        .build(tauri::generate_context!())
        .expect("ошибка запуска FM27 Analyst");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(mut child) = handle.state::<Core>().0.lock().unwrap().take() {
                let _ = child.kill();
            }
        }
    });
}
