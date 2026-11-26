using System;
using System.Collections.Generic;
using System.Text.Json;
using FM27Bridge.Core;

// Простой раннер без NuGet: dotnet run --project tests/FM27Bridge.Tests
internal static class Program
{
    private static int _failed, _passed;

    private static void Check(bool ok, string name)
    {
        if (ok) _passed++;
        else { _failed++; Console.WriteLine("FAIL: " + name); }
    }

    private sealed class FakeTransport : ITransport
    {
        public bool Up = true;
        public string PollJson = "{\"commands\":[]}";
        public readonly List<(string path, string json)> Posts = new List<(string, string)>();
        public int Polls;
        public string? LastError => Up ? null : "offline";

        public string? Get(string path)
        {
            if (!Up) return null;
            Polls++;
            var r = PollJson;
            PollJson = "{\"commands\":[]}";
            return r;
        }

        public bool Post(string path, string json)
        {
            if (!Up) return false;
            Posts.Add((path, json));
            return true;
        }
    }

    private static int Main()
    {
        ClientHandshakeAndCommands();
        ClientKeepsOutboxWhileOffline();
        ClientDropsOldestWhenOutboxFull();
        DumpSortsDedupesAndHashes();
        TopStripPicksHeader();
        Console.WriteLine($"{_passed} passed, {_failed} failed");
        return _failed == 0 ? 0 : 1;
    }

    private static void ClientHandshakeAndCommands()
    {
        var t = new FakeTransport
        {
            PollJson = "{\"commands\":[{\"id\":\"c1\",\"type\":\"grab_table\"},{\"id\":\"c2\",\"type\":\"screen\"}],\"auto_screen\":true,\"auto_interval_sec\":0.2}",
        };
        var c = new BridgeClient(t, new Hello { PluginVersion = "0.1.0", GameVersion = "27.1" });
        c.Step();
        Check(t.Posts.Count == 1 && t.Posts[0].path == "api/bridge/hello", "hello first");
        Check(t.Posts[0].json.Contains("\"plugin_version\":\"0.1.0\""), "hello json uses snake_case names");
        Check(c.Connected, "connected after poll");
        Check(c.AutoScreen && c.AutoIntervalSec == 1, "auto settings applied, interval clamped to 1s");
        Check(c.TryNextCommand(out var a) && a.Id == "c1" && a.Type == "grab_table", "first command");
        Check(c.TryNextCommand(out var b) && b.Id == "c2", "second command");
        Check(!c.TryNextCommand(out _), "queue empty");
        c.Step();
        Check(t.Posts.Count == 1, "hello not repeated while connected");
    }

    private static void ClientKeepsOutboxWhileOffline()
    {
        var t = new FakeTransport();
        var c = new BridgeClient(t, new Hello());
        c.Step();
        t.Up = false;
        c.Send("api/bridge/table", new TablePayload { Screen = "Squad", Headers = { "Имя" } });
        c.Step();
        Check(!c.Connected, "offline detected");
        t.Up = true;
        c.Step();
        Check(t.Posts.Count == 3, "re-hello after reconnect + table delivered");
        Check(t.Posts[1].path == "api/bridge/hello" && t.Posts[2].path == "api/bridge/table", "order: hello, then table");
        var table = JsonSerializer.Deserialize<TablePayload>(t.Posts[2].json)!;
        Check(table.Headers.Count == 1 && table.Headers[0] == "Имя", "cyrillic survives json");
        Check(!t.Posts[2].json.Contains("command_id"), "null fields omitted");
    }

    private static void ClientDropsOldestWhenOutboxFull()
    {
        var t = new FakeTransport { Up = false };
        var c = new BridgeClient(t, new Hello()) { MaxOutbox = 3 };
        for (var i = 0; i < 5; i++)
            c.Send("api/bridge/screen", new ScreenPayload { Hash = "h" + i });
        t.Up = true;
        c.Step();
        var screens = t.Posts.FindAll(p => p.path == "api/bridge/screen");
        Check(screens.Count == 3, "outbox capped");
        Check(screens[0].json.Contains("\"h2\"") && screens[2].json.Contains("\"h4\""), "newest kept");
    }

    private static void DumpSortsDedupesAndHashes()
    {
        var raw = new List<ScreenText>
        {
            new ScreenText { Text = "Статистика", X = 50, Y = 300 },
            new ScreenText { Text = "  <b>2</b> - 1 ", X = 400, Y = 20 },
            new ScreenText { Text = "67'", X = 600, Y = 21 },
            new ScreenText { Text = "Статистика", X = 50, Y = 300 }, // дубль
            new ScreenText { Text = "", X = 1, Y = 1 },
        };
        var p = ScreenDump.Build(raw, 100, "Match", 1920, 1080);
        Check(p.Texts.Count == 3, "empty and duplicate removed");
        Check(p.Texts[0].Text == "2 - 1" && p.Texts[1].Text == "67'", "rich-text tags stripped, top row first, left to right");
        var moved = ScreenDump.Build(new List<ScreenText>
        {
            new ScreenText { Text = "2 - 1", X = 401, Y = 21 },
            new ScreenText { Text = "67'", X = 601, Y = 22 },
            new ScreenText { Text = "Статистика", X = 51, Y = 301 },
        }, 100, "Match", 1920, 1080);
        Check(p.Hash == moved.Hash, "1px jitter does not change hash");
        var changed = ScreenDump.Build(new List<ScreenText>
        {
            new ScreenText { Text = "2 - 1", X = 400, Y = 20 },
            new ScreenText { Text = "68'", X = 600, Y = 21 },
            new ScreenText { Text = "Статистика", X = 50, Y = 300 },
        }, 100, "Match", 1920, 1080);
        Check(p.Hash != changed.Hash, "minute change changes hash");
        var cut = ScreenDump.Build(raw, 2, "Match", 1920, 1080);
        Check(cut.Truncated && cut.Texts.Count == 2, "truncation flagged");
    }

    private static void TopStripPicksHeader()
    {
        var texts = new List<ScreenText>
        {
            new ScreenText { Text = "Чт 26 ноя 2026", X = 10, Y = 10 },
            new ScreenText { Text = "Продолжить", X = 1700, Y = 30 },
            new ScreenText { Text = "Иванов", X = 100, Y = 500 },
        };
        var top = ScreenDump.TopStrip(texts, 1080);
        Check(top.Count == 2 && top[0] == "Чт 26 ноя 2026", "top strip only");
    }
}
