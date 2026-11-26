using System;
using System.Collections.Generic;
using System.Threading;
using FM27Bridge.Core;

// Изображает плагин: представляется ядру, ждёт команды и отвечает данными-примерами.
var url = args.Length > 0 ? args[0] : "http://127.0.0.1:8727";
var seconds = args.Length > 1 ? int.Parse(args[1]) : 30;
using var transport = new HttpTransport(url, TimeSpan.FromSeconds(3));
var client = new BridgeClient(transport, new Hello { PluginVersion = "fake", GameVersion = "27.0-fake", Product = "Fake FM27" },
    m => Console.WriteLine("[bridge] " + m)) { PollInterval = TimeSpan.FromMilliseconds(200) };
client.Start();
var until = DateTime.UtcNow.AddSeconds(seconds);
while (DateTime.UtcNow < until)
{
    while (client.TryNextCommand(out var cmd))
    {
        Console.WriteLine($"command {cmd.Type} {cmd.Id}");
        if (cmd.Type == "grab_table")
            client.Send("api/bridge/table", new TablePayload
            {
                CommandId = cmd.Id, Screen = "Squad", ExpectedRows = 1,
                Headers = new List<string> { "Имя", "Возраст", "Позиция", "Дриблинг" },
                Rows = new List<List<string>> { new List<string> { "Тест Тестов", "20", "АП (Ц)", "13" } },
                ContextTexts = new List<string> { "Чт 26 ноя 2026" },
            });
        else if (cmd.Type == "screen")
        {
            var s = ScreenDump.Build(new[] { new ScreenText { Text = "Чт 26 ноя 2026", X = 5, Y = 5 } }, 100, "Match", 1920, 1080);
            s.CommandId = cmd.Id;
            client.Send("api/bridge/screen", s);
        }
        else
            client.Send("api/bridge/result", new ResultPayload { CommandId = cmd.Id, Ok = false, Message = "fake: не умею " + cmd.Type });
    }
    Thread.Sleep(50);
}
Console.WriteLine(client.Connected ? "connected" : "not connected");
