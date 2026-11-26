using System;
using System.Collections.Generic;
using System.Linq;
using FM27Bridge.Core;
using FM27Exporter;
using FM27Exporter.Core;
using UnityEngine;

namespace FM27Bridge
{
    /// <summary>
    /// Забирает таблицу с экрана целиком. Список в FM виртуальный (строки создаются при прокрутке),
    /// поэтому, как и FM27 Exporter, прокручиваем его по кадрам и возвращаем прокрутку на место.
    /// Это единственное, что мост делает с интерфейсом; данные игры не меняются.
    /// </summary>
    internal sealed class TableGrab
    {
        private readonly string _commandId;
        private readonly TableView _view;
        private readonly List<TableView.Column> _columns;
        private readonly ScrollCollector _collector;
        private readonly Vector2 _originalOffset;
        private readonly int? _expected;
        private readonly bool _paginated;
        private readonly List<string> _context;

        public bool Finished { get; private set; }
        public object? Result { get; private set; }
        public string Status { get; private set; } = "";

        private TableGrab(string commandId, TableView view, List<TableView.Column> columns, List<string> context)
        {
            _commandId = commandId;
            _view = view;
            _columns = columns;
            _context = context;
            _originalOffset = view.Rows.scrollOffset;
            _expected = view.ItemCount;
            _paginated = view.IsPaginated;
            var options = new ScrollCollectorOptions { StableFrames = 3, MaxSettleFrames = 90, MaxSettleSeconds = 2.0, MaxRows = 25000 };
            _collector = new ScrollCollector(new GameList(view), columns.Count, CellMapping, _expected, options,
                m => Plugin.Logger.LogInfo(m));
        }

        public static List<TableView> Tables() => TableView.FindAll(out _);

        public static TableGrab? Start(string commandId, int? index, List<string> context, out string message)
        {
            var tables = Tables();
            if (tables.Count == 0)
            {
                message = "На экране нет таблицы. Откройте состав, поиск игроков или шорт-лист.";
                return null;
            }
            TableView view;
            if (index.HasValue && index.Value >= 0 && index.Value < tables.Count)
                view = tables[index.Value];
            else
                view = TableView.UnderPointer(tables) ?? tables[0]; // самая большая
            var columns = view.ReadColumns();
            if (columns.Count == 0)
            {
                message = "Таблица ещё загружается — попробуйте через секунду.";
                return null;
            }
            message = string.Empty;
            Plugin.Logger.LogInfo($"Забираю '{view.ScreenName()}': {columns.Count} колонок, {view.ItemCount?.ToString() ?? "?"} строк.");
            return new TableGrab(commandId, view, columns, context);
        }

        public void Tick()
        {
            if (Finished)
                return;
            try
            {
                if (_view.Table.panel == null)
                {
                    Fail("Таблица закрыта до окончания чтения.");
                    return;
                }
                var now = _view.ItemCount;
                if (_expected.HasValue && now.HasValue && now.Value != _expected.Value)
                {
                    Fail($"Список изменился во время чтения ({_expected} → {now} строк). Повторите.");
                    return;
                }
                _collector.Tick();
                var total = _collector.Expected.HasValue ? $"/{_collector.Expected}" : "";
                Status = $"FM27 Analyst: читаю таблицу… {_collector.Count}{total}";
                if (_collector.Finished)
                    Finish();
            }
            catch (Exception ex)
            {
                Plugin.Logger.LogError($"Чтение таблицы: {ex}");
                Fail("Ошибка чтения таблицы: " + ex.Message);
            }
        }

        public void Cancel()
        {
            if (!Finished)
                Fail("Чтение отменено.");
        }

        private void Fail(string message)
        {
            Restore();
            Finished = true;
            Status = "FM27 Analyst: " + message;
            Result = new ResultPayload { CommandId = _commandId, Ok = false, Message = message };
        }

        private int[] CellMapping(int cellsPerRow)
        {
            var map = new int[_columns.Count];
            var visible = _columns.Count(c => !c.Hidden);
            var byVisible = cellsPerRow != _columns.Count && cellsPerRow == visible;
            var v = 0;
            for (var c = 0; c < _columns.Count; c++)
                map[c] = byVisible ? (_columns[c].Hidden ? -1 : v++) : _columns[c].Index;
            return map;
        }

        private void Finish()
        {
            Restore();
            Finished = true;
            var expected = _paginated ? null : _collector.Expected;
            var missing = _collector.Rows.MissingIndices(expected ?? -1);
            var keep = new List<int>();
            var payload = new TablePayload
            {
                CommandId = _commandId,
                Screen = _view.ScreenName(),
                Path = Diagnostics.Path(_view.Table),
                ExpectedRows = expected,
                Paginated = _paginated,
                MissingRows = missing.Count,
                ContextTexts = _context,
            };
            for (var c = 0; c < _columns.Count; c++)
            {
                if (_columns[c].Hidden)
                    continue;
                keep.Add(c);
                payload.Headers.Add(_columns[c].Header);
            }
            payload.HiddenColumns = _columns.Count - keep.Count;
            foreach (var r in _collector.Rows.Rows())
            {
                var cells = new List<string>(keep.Count);
                foreach (var k in keep)
                    cells.Add(k < r.Count ? r[k] ?? "" : "");
                payload.Rows.Add(cells);
            }
            if (_paginated)
                payload.Notes.Add("Список разбит на страницы: прочитана только текущая страница.");
            if (payload.HiddenColumns > 0)
                payload.Notes.Add($"{payload.HiddenColumns} колонок игра скрыла из-за ширины окна — расширьте окно, чтобы они попали в данные.");
            if (_collector.UnsettledPages > 0)
                payload.Notes.Add($"{_collector.UnsettledPages} шагов прокрутки прочитаны до полной загрузки строк — значения стоит проверить.");
            Status = $"FM27 Analyst: отправлено {payload.Rows.Count} строк × {payload.Headers.Count} колонок.";
            Result = payload;
        }

        private void Restore()
        {
            try { _view.Rows.scrollOffset = _originalOffset; }
            catch (Exception ex) { Plugin.Logger.LogWarning($"Прокрутка не восстановлена: {ex.Message}"); }
        }

        private sealed class GameList : IScrollList
        {
            private readonly TableView _view;

            public GameList(TableView view) => _view = view;

            public float ScrollY => _view.Rows.scrollOffset.y;
            public float ViewportHeight => _view.Rows.contentViewport.layout.height;
            public float ContentHeight => _view.Rows.contentContainer.layout.height;

            public float MaxScroll
            {
                get
                {
                    var scroll = _view.Rows;
                    var max = scroll.contentContainer.layout.height - scroll.contentViewport.layout.height;
                    try
                    {
                        var high = scroll.verticalScroller.highValue;
                        if (!float.IsNaN(high) && high > max)
                            max = high;
                    }
                    catch
                    {
                    }
                    return float.IsNaN(max) ? 0f : Math.Max(0f, max);
                }
            }

            public void ScrollTo(float y)
            {
                var current = _view.Rows.scrollOffset;
                _view.Rows.scrollOffset = new Vector2(current.x, y);
            }

            public IReadOnlyList<IVisibleRow> VisibleRows()
            {
                var rows = _view.VisibleRows();
                var result = new List<IVisibleRow>(rows.Count);
                foreach (var r in rows)
                    result.Add(new Row(r));
                return result;
            }

            private sealed class Row : IVisibleRow
            {
                private readonly TableView.VisibleRow _row;
                private readonly string?[] _texts;

                public Row(TableView.VisibleRow row)
                {
                    _row = row;
                    _texts = new string?[row.Cells.Count];
                }

                public float ContentY => _row.ContentY;
                public float Height => _row.Height;
                public int CellCount => _row.Cells.Count;
                public string Cell(int index) => _texts[index] ??= TableView.ReadCell(_row.Cells[index]);
                public bool Selected => _row.Selected;
            }
        }
    }
}
