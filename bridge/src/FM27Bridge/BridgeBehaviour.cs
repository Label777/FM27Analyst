using System;
using System.Collections.Generic;
using FM27Bridge.Core;
using FM27Exporter;
using UnityEngine;

namespace FM27Bridge
{
    /// <summary>Тонкая обёртка Unity: только передаёт кадры контроллеру.</summary>
    public class BridgeBehaviour : MonoBehaviour
    {
        private Controller? _controller;

        public BridgeBehaviour(IntPtr pointer) : base(pointer)
        {
        }

        public void Start() => _controller = new Controller();
        public void Update() => _controller?.Update();
        public void OnGUI() => _controller?.OnGUI();
        public void OnDestroy() => _controller?.Dispose();
    }

    /// <summary>Вся логика моста — в обычном управляемом классе (Il2CppInterop не регистрирует методы с управляемыми параметрами).</summary>
    internal sealed class Controller : IDisposable
    {
        private const float MessageSeconds = 6f;

        private BridgeClient? _client;
        private TableGrab? _grab;
        private string _message = "";
        private float _messageUntil;
        private float _nextAuto;
        private string _lastAutoHash = "";
        private bool _slowWarned;
        private string? _sniffCommand;

        public Controller()
        {
            var hello = new Hello
            {
                PluginVersion = Plugin.Version,
                GameVersion = Application.version,
                UnityVersion = Application.unityVersion,
                Product = Application.productName,
            };
            _client = new BridgeClient(new HttpTransport(Plugin.CoreUrl.Value, TimeSpan.FromSeconds(3)), hello,
                m => Plugin.Logger.LogInfo(m));
            _client.Start();
            Plugin.Logger.LogInfo($"Мост запущен, подключаюсь к {Plugin.CoreUrl.Value}.");
        }

        public void Dispose()
        {
            if (Sniffer.Active)
                Sniffer.Stop();
            _client?.Dispose();
        }

        public void Update()
        {
            var client = _client;
            if (client == null)
                return;
            try
            {
                var sniffDone = Sniffer.Tick();
                if (sniffDone != null)
                {
                    Plugin.Logger.LogInfo($"{sniffDone} → {Sniffer.File}");
                    client.Send("api/bridge/result", new ResultPayload { CommandId = _sniffCommand, Ok = true, Message = sniffDone, Detail = Sniffer.File });
                    Show("FM27 Analyst: " + sniffDone, MessageSeconds);
                }
                if (_grab != null)
                {
                    _grab.Tick();
                    Show(_grab.Status, _grab.Finished ? MessageSeconds : 1f);
                    if (_grab.Finished)
                    {
                        if (_grab.Result is TablePayload t)
                            client.Send("api/bridge/table", t);
                        else if (_grab.Result != null)
                            client.Send("api/bridge/result", _grab.Result);
                        _grab = null;
                    }
                    return; // пока читаем таблицу — других команд не берём
                }
                if (client.TryNextCommand(out var cmd))
                    Run(client, cmd);
                else if (client.AutoScreen && client.Connected && Time.unscaledTime >= _nextAuto)
                    AutoScreen(client);
            }
            catch (Exception ex)
            {
                Plugin.Logger.LogError($"{Plugin.Name}: {ex}");
                try { _grab?.Cancel(); } catch { }
                _grab = null;
            }
        }

        private void Run(BridgeClient client, Command cmd)
        {
            switch (cmd.Type)
            {
                case "grab_table":
                    var context = TopTexts();
                    _grab = TableGrab.Start(cmd.Id, cmd.TableIndex, context, out var why);
                    if (_grab == null)
                    {
                        client.Send("api/bridge/result", new ResultPayload { CommandId = cmd.Id, Ok = false, Message = why });
                        Show("FM27 Analyst: " + why, MessageSeconds);
                    }
                    break;
                case "screen":
                    var screen = ScreenReader.Read(Plugin.MaxTexts.Value, out var ms);
                    screen.CommandId = cmd.Id;
                    client.Send("api/bridge/screen", screen);
                    Plugin.Logger.LogInfo($"Экран '{screen.Screen}': {screen.Texts.Count} текстов за {ms} мс.");
                    Show($"FM27 Analyst: экран отправлен ({screen.Texts.Count} текстов).", MessageSeconds);
                    break;
                case "tables":
                    var list = new TablesPayload { CommandId = cmd.Id };
                    var tables = TableGrab.Tables();
                    for (var i = 0; i < tables.Count; i++)
                    {
                        var t = tables[i];
                        list.Tables.Add(new TableInfo
                        {
                            Index = i,
                            Screen = t.ScreenName(),
                            Name = t.Table.name ?? "",
                            Columns = t.ReadColumns().Count,
                            Rows = t.ItemCount,
                            Area = Ui.Area(t.Table),
                        });
                    }
                    client.Send("api/bridge/tables", list);
                    break;
                case "sniff":
                case "probe":
                    var started = cmd.Type == "probe" ? Sniffer.StartProbe(25f) : Sniffer.Start(60f);
                    _sniffCommand = cmd.Id;
                    Plugin.Logger.LogInfo(started);
                    Show("FM27 Analyst: " + started, MessageSeconds);
                    client.Send("api/bridge/result", new ResultPayload { CommandId = null, Ok = true, Message = started });
                    break;
                case "explore":
                    Show("FM27 Analyst: разведка движка…", 3f);
                    var file = Explorer.Run(out var summary);
                    Plugin.Logger.LogInfo($"Справочник движка ({summary}) → {file}");
                    client.Send("api/bridge/result", new ResultPayload { CommandId = cmd.Id, Ok = true, Message = $"Справочник движка: {summary}", Detail = file });
                    Show("FM27 Analyst: справочник движка сохранён.", MessageSeconds);
                    break;
                default:
                    client.Send("api/bridge/result", new ResultPayload
                    {
                        CommandId = cmd.Id, Ok = false, Message = $"Неизвестная команда '{cmd.Type}' — обновите плагин.",
                    });
                    break;
            }
        }

        private void AutoScreen(BridgeClient client)
        {
            var screen = ScreenReader.Read(Plugin.MaxTexts.Value, out var ms);
            var interval = (float)client.AutoIntervalSec;
            if (ms > 80)
            {
                // Чтение экрана не должно тормозить игру: если оно дорогое, читаем реже.
                interval = Math.Max(interval, ms / 1000f * 40f);
                if (!_slowWarned)
                {
                    Plugin.Logger.LogWarning($"Снимок экрана занял {ms} мс — авто-режим будет реже (раз в {interval:0.#} с).");
                    _slowWarned = true;
                }
            }
            _nextAuto = Time.unscaledTime + interval;
            if (screen.Hash == _lastAutoHash)
                return; // ничего не изменилось
            _lastAutoHash = screen.Hash;
            screen.Auto = true;
            client.Send("api/bridge/screen", screen);
        }

        private static List<string> TopTexts()
        {
            try
            {
                var screen = ScreenReader.Read(400, out _);
                return ScreenDump.TopStrip(screen.Texts, screen.Height);
            }
            catch (Exception ex)
            {
                Plugin.Logger.LogDebug($"Верхняя полоса не прочитана: {ex.Message}");
                return new List<string>();
            }
        }

        public void OnGUI()
        {
            if (!Plugin.ShowStatus.Value || _message.Length == 0 || Time.unscaledTime > _messageUntil)
                return;
            try
            {
                var box = GUI.skin.box;
                int size = box.fontSize; bool wrap = box.wordWrap; var align = box.alignment;
                box.fontSize = 15; box.wordWrap = true; box.alignment = TextAnchor.MiddleCenter;
                var width = Math.Min(Screen.width - 40, 760);
                GUI.Box(new Rect((Screen.width - width) / 2f, 84, width, 44), _message, box);
                box.fontSize = size; box.wordWrap = wrap; box.alignment = align;
            }
            catch
            {
            }
        }

        private void Show(string message, float seconds)
        {
            _message = message;
            _messageUntil = Time.unscaledTime + seconds;
        }
    }
}
