"""Сбор датасета скриншотов FM27 (этап 3).

Самый простой способ — автосъёмка: запустить и просто играть.

    python tools/collect_screens.py --out dataset --auto 4

Снимок окна FM27 раз в 4 секунды, только если экран изменился. Остановить — Ctrl+C.

Ручной режим с метками (если хочется сразу разложить по типам):

    python tools/collect_screens.py --out dataset

Затем в игре нажимайте сочетание для того экрана, который сейчас открыт:

    Ctrl+Alt+1  матч (2D/3D + плашка счёта)
    Ctrl+Alt+2  статистика матча
    Ctrl+Alt+3  тактика (в владении / без мяча)
    Ctrl+Alt+4  состав / панель игроков с усталостью
    Ctrl+Alt+5  профиль игрока
    Ctrl+Alt+6  анализ: тепловые карты, Action Zones, Pass Maps
    Ctrl+Alt+7  превью соперника
    Ctrl+Alt+8  лента dugout (сообщения штаба) крупно
    Ctrl+Alt+0  другое
    Ctrl+Alt+Q  выход

Каждый снимок сохраняется как PNG + JSON с меткой, разрешением, языком и
масштабом интерфейса. Проверить, чего не хватает:

    python tools/collect_screens.py --out dataset --report
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

LABELS = {
    "1": "match",
    "2": "match_stats",
    "3": "tactics",
    "4": "squad",
    "5": "player_profile",
    "6": "analysis",
    "7": "opponent_preview",
    "8": "dugout",
    "0": "other",
}
LABEL_RU = {
    "match": "матч",
    "match_stats": "статистика матча",
    "tactics": "тактика",
    "squad": "состав/усталость",
    "player_profile": "профиль игрока",
    "analysis": "анализ (карты)",
    "opponent_preview": "превью соперника",
    "dugout": "лента dugout",
    "other": "другое",
}
# Минимум снимков на тип экрана для обучения классификатора на одном разрешении
TARGET = {
    "match": 60, "match_stats": 60, "tactics": 40, "squad": 50, "player_profile": 30,
    "analysis": 30, "opponent_preview": 20, "dugout": 40, "other": 30,
}


def report(out: Path) -> None:
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in out.rglob("*.json")]
    by_label = Counter(m["label"] for m in metas)
    by_res = Counter(f"{m['width']}x{m['height']} @{m.get('ui_scale', '?')}%" for m in metas)
    print(f"\nВсего снимков: {len(metas)}\n")
    print(f"{'Экран':<22}{'есть':>6}{'нужно':>8}")
    for label, need in TARGET.items():
        have = by_label.get(label, 0)
        mark = "  ✓" if have >= need else ""
        print(f"{LABEL_RU[label]:<22}{have:>6}{need:>8}{mark}")
    if by_label.get("unsorted"):
        print(f"{'неразмеченные (авто)':<22}{by_label['unsorted']:>6}{'—':>8}")
    print("\nРазрешения и масштабы:")
    for k, v in by_res.most_common():
        print(f"  {k}: {v}")
    print("\nЦель этапа 3: каждый тип экрана на 1080p, 1440p и 4K, масштаб 100% и 125–150%, русский интерфейс.")


def auto_capture(src, save, every: float, limit: int, counts: Counter) -> None:
    """Автосъёмка: снимок раз в `every` секунд, только если экран заметно изменился.

    Пользователь просто играет; снимки попадают в папку unsorted,
    разметку по типам экранов делаем потом.
    """
    from fm27_analyst.vision import ChangeFilter

    cf = ChangeFilter(threshold=10)
    print(
        f"Автосъёмка каждые {every:g} с (только изменившиеся экраны, максимум {limit}). "
        "Просто играйте: матчи, тактика, состав, профили игроков. Остановить — Ctrl+C."
    )
    misses = 0
    try:
        while counts["unsorted"] < limit:
            time.sleep(every)
            try:
                img = src.grab()
            except Exception as e:
                misses += 1
                if misses in (1, 10) or misses % 60 == 0:
                    print(f"  … окно FM27 недоступно ({e}) — жду")
                continue
            misses = 0
            if cf.changed(img):
                save(img, "unsorted")
    except KeyboardInterrupt:
        pass
    print(f"\nСнято: {counts['unsorted']}. Заархивируйте папку с датасетом и пришлите — разметку сделаю сам.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Сбор скриншотов FM27 для обучения распознавания")
    ap.add_argument("--out", type=Path, default=ROOT / "dataset")
    ap.add_argument("--lang", default="ru", help="язык интерфейса FM27 (ru/en)")
    ap.add_argument("--ui-scale", type=int, default=None, help="масштаб интерфейса FM27, %")
    ap.add_argument("--report", action="store_true", help="показать, каких снимков не хватает")
    ap.add_argument("--auto", type=float, default=0, metavar="СЕК",
                    help="автосъёмка: снимок раз в СЕК секунд, если экран изменился (без горячих клавиш)")
    ap.add_argument("--max", type=int, default=800, help="предел снимков в автосъёмке")
    args = ap.parse_args()

    if args.report:
        report(args.out)
        return

    from fm27_analyst.capture import CaptureError, get_default_source

    ui_scale = args.ui_scale
    if ui_scale is None:
        raw = input("Масштаб интерфейса FM27 в процентах (Enter = 100): ").strip()
        ui_scale = int(raw) if raw.isdigit() else 100

    try:
        src = get_default_source()
    except CaptureError as e:
        sys.exit(str(e))
    counts: Counter[str] = Counter()

    def save(img, label: str) -> None:
        folder = args.out / label
        folder.mkdir(parents=True, exist_ok=True)
        stem = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
        img.save(folder / f"{stem}.png")
        meta = {
            "label": label,
            "width": img.size[0],
            "height": img.size[1],
            "lang": args.lang,
            "ui_scale": ui_scale,
            "captured_at": time.time(),
            "source": src.name,
        }
        (folder / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        counts[label] += 1
        print(f"  + {LABEL_RU.get(label, label)} ({img.size[0]}×{img.size[1]}) — в этой сессии: {counts[label]}")

    if args.auto:
        auto_capture(src, save, args.auto, args.max, counts)
        return

    try:
        import keyboard  # type: ignore
    except ImportError:
        sys.exit("Нужен пакет keyboard:  pip install -e core[windows]")

    def shoot(label: str) -> None:
        try:
            img = src.grab()
        except Exception as e:  # окно свёрнуто и т.п.
            print(f"  ! не удалось сделать снимок: {e}")
            return
        save(img, label)

    print(f"Источник захвата: {src.name}. Откройте FM27 и нажимайте Ctrl+Alt+цифра. Выход — Ctrl+Alt+Q.")
    for key, label in LABELS.items():
        keyboard.add_hotkey(f"ctrl+alt+{key}", shoot, args=(label,))
    keyboard.wait("ctrl+alt+q")
    print("\nГотово.")
    report(args.out)


if __name__ == "__main__":
    main()
