using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace FM27Bridge.Core
{
    // Обмен с ядром FM27 Analyst (127.0.0.1:8727). Мост только ЧИТАЕТ интерфейс игры:
    // ни одна команда не нажимает кнопки, не меняет тактику, состав или сейв.

    public sealed class Hello
    {
        [JsonPropertyName("plugin_version")] public string PluginVersion { get; set; } = "";
        [JsonPropertyName("game_version")] public string GameVersion { get; set; } = "";
        [JsonPropertyName("unity_version")] public string UnityVersion { get; set; } = "";
        [JsonPropertyName("product")] public string Product { get; set; } = "";
    }

    public sealed class Command
    {
        [JsonPropertyName("id")] public string Id { get; set; } = "";
        // grab_table — таблица на экране целиком (с прокруткой списка), screen — все тексты экрана,
        // tables — какие таблицы сейчас видны, diagnose — дерево интерфейса для настройки распознавания.
        [JsonPropertyName("type")] public string Type { get; set; } = "";
        [JsonPropertyName("table_index")] public int? TableIndex { get; set; }
    }

    public sealed class PollReply
    {
        [JsonPropertyName("commands")] public List<Command> Commands { get; set; } = new List<Command>();
        // Авто-режим: раз в N секунд присылать тексты экрана, если экран изменился (для живого матча).
        [JsonPropertyName("auto_screen")] public bool AutoScreen { get; set; }
        [JsonPropertyName("auto_interval_sec")] public double AutoIntervalSec { get; set; } = 3;
    }

    public sealed class ScreenText
    {
        [JsonPropertyName("t")] public string Text { get; set; } = "";
        [JsonPropertyName("path")] public string Path { get; set; } = "";
        [JsonPropertyName("cls")] public string Classes { get; set; } = "";
        [JsonPropertyName("x")] public float X { get; set; }
        [JsonPropertyName("y")] public float Y { get; set; }
        [JsonPropertyName("w")] public float W { get; set; }
        [JsonPropertyName("h")] public float H { get; set; }
    }

    public sealed class ScreenPayload
    {
        [JsonPropertyName("command_id")] public string? CommandId { get; set; }
        [JsonPropertyName("auto")] public bool Auto { get; set; }
        [JsonPropertyName("screen")] public string Screen { get; set; } = "";
        [JsonPropertyName("hash")] public string Hash { get; set; } = "";
        [JsonPropertyName("truncated")] public bool Truncated { get; set; }
        [JsonPropertyName("width")] public float Width { get; set; }
        [JsonPropertyName("height")] public float Height { get; set; }
        [JsonPropertyName("texts")] public List<ScreenText> Texts { get; set; } = new List<ScreenText>();
    }

    public sealed class TableInfo
    {
        [JsonPropertyName("index")] public int Index { get; set; }
        [JsonPropertyName("screen")] public string Screen { get; set; } = "";
        [JsonPropertyName("name")] public string Name { get; set; } = "";
        [JsonPropertyName("columns")] public int Columns { get; set; }
        [JsonPropertyName("rows")] public int? Rows { get; set; }
        [JsonPropertyName("area")] public float Area { get; set; }
    }

    public sealed class TablePayload
    {
        [JsonPropertyName("command_id")] public string? CommandId { get; set; }
        [JsonPropertyName("screen")] public string Screen { get; set; } = "";
        [JsonPropertyName("path")] public string Path { get; set; } = "";
        [JsonPropertyName("headers")] public List<string> Headers { get; set; } = new List<string>();
        [JsonPropertyName("rows")] public List<List<string>> Rows { get; set; } = new List<List<string>>();
        [JsonPropertyName("expected_rows")] public int? ExpectedRows { get; set; }
        [JsonPropertyName("paginated")] public bool Paginated { get; set; }
        [JsonPropertyName("hidden_columns")] public int HiddenColumns { get; set; }
        [JsonPropertyName("missing_rows")] public int MissingRows { get; set; }
        [JsonPropertyName("notes")] public List<string> Notes { get; set; } = new List<string>();
        // Строка вверху экрана (дата в игре и т.п.) — ядро само ищет в ней игровую дату.
        [JsonPropertyName("context_texts")] public List<string> ContextTexts { get; set; } = new List<string>();
    }

    public sealed class TablesPayload
    {
        [JsonPropertyName("command_id")] public string? CommandId { get; set; }
        [JsonPropertyName("tables")] public List<TableInfo> Tables { get; set; } = new List<TableInfo>();
    }

    public sealed class ResultPayload
    {
        [JsonPropertyName("command_id")] public string? CommandId { get; set; }
        [JsonPropertyName("ok")] public bool Ok { get; set; }
        [JsonPropertyName("message")] public string Message { get; set; } = "";
        [JsonPropertyName("detail")] public string? Detail { get; set; }
    }
}
