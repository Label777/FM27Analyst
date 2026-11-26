using System;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using UnityEngine;

namespace FM27Bridge
{
    [BepInPlugin(Guid, Name, Version)]
    public class Plugin : BasePlugin
    {
        public const string Guid = "local.fm27analyst.bridge";
        public const string Name = "FM27 Analyst Bridge";
        public const string Version = "0.1.1";

        internal static ManualLogSource Logger { get; private set; } = null!;
        internal static ConfigEntry<string> CoreUrl { get; private set; } = null!;
        internal static ConfigEntry<int> MaxTexts { get; private set; } = null!;
        internal static ConfigEntry<bool> ShowStatus { get; private set; } = null!;

        public override void Load()
        {
            Logger = Log;
            FM27Exporter.Plugin.Logger = Log;
            CoreUrl = Config.Bind("Connection", "CoreUrl", "http://127.0.0.1:8727",
                "Адрес ядра FM27 Analyst. Мост работает только с этим компьютером.");
            MaxTexts = Config.Bind("Screen", "MaxTexts", 3000, "Сколько текстов экрана отправлять за один снимок.");
            ShowStatus = Config.Bind("Display", "ShowStatus", true, "Показывать вверху экрана короткое сообщение, когда данные отправлены.");
            if (!CoreUrl.Value.StartsWith("http://127.0.0.1", StringComparison.Ordinal) &&
                !CoreUrl.Value.StartsWith("http://localhost", StringComparison.Ordinal))
            {
                Logger.LogWarning("CoreUrl должен указывать на этот компьютер — возвращаю http://127.0.0.1:8727.");
                CoreUrl.Value = "http://127.0.0.1:8727";
            }
            Logger.LogInfo($"{Name} {Version}: игра {Application.productName} {Application.version}, Unity {Application.unityVersion}. " +
                           $"Ядро: {CoreUrl.Value}. Режим: только чтение интерфейса.");
            AddComponent<BridgeBehaviour>();
        }
    }
}

namespace FM27Exporter
{
    // Прослойка для исходников FM27 Exporter (MIT), которые мост использует без изменений.
    internal static class Plugin
    {
        internal static ManualLogSource Logger = null!;
    }

    internal static class Diagnostics
    {
        internal static string Path(UnityEngine.UIElements.VisualElement e)
        {
            var parts = new System.Collections.Generic.List<string>();
            for (var x = e; x != null && parts.Count < 16; x = x.parent)
                if (!string.IsNullOrEmpty(x.name))
                    parts.Add("#" + x.name);
            parts.Reverse();
            return string.Join(" > ", parts);
        }
    }
}
