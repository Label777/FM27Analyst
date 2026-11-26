using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using FM.GamePlugin;
using HarmonyLib;
using SI.Bindable;
using SI.Bindable.Reference.Core;
using SI.Core;
using SI.Interop;

namespace FM27Bridge
{
    /// <summary>
    /// Запись обмена «интерфейс ↔ движок» на короткое время: какие записи (игрок, клуб…) и какие свойства
    /// интерфейс запрашивает у движка. Только наблюдение: перехватчики пишут в файл и ничего не меняют.
    /// Нужна, чтобы научиться самим запрашивать у движка данные игроков (вся база, как в Genie Scout).
    /// </summary>
    internal static class Sniffer
    {
        private const int MaxLines = 40000;
        private static Harmony? _harmony;
        private static StreamWriter? _out;
        private static int _lines;
        private static float _until;
        private static readonly Dictionary<string, int> Counts = new Dictionary<string, int>();

        public static bool Active => _out != null;
        public static string? File { get; private set; }

        public static string Start(float seconds)
        {
            if (Active)
                return "Запись уже идёт.";
            var dir = Path.Combine(BepInEx.Paths.PluginPath, "FM27AnalystBridge");
            Directory.CreateDirectory(dir);
            File = Path.Combine(dir, $"sniff-{System.DateTime.Now:yyyyMMdd-HHmmss}.txt");
            _out = new StreamWriter(File, false, new UTF8Encoding(false)) { AutoFlush = false };
            _out.WriteLine($"# FM27 interop sniff {System.DateTime.Now:yyyy-MM-dd HH:mm:ss}, game {UnityEngine.Application.version}");
            _lines = 0;
            Counts.Clear();
            _until = UnityEngine.Time.unscaledTime + seconds;
            _harmony ??= new Harmony(Plugin.Guid + ".sniff");
            _harmony.PatchAll(typeof(Patches));
            return $"Запись обмена с движком: {seconds:0} с. Откройте в игре профиль игрока и вкладку атрибутов.";
        }

        /// <summary>Вызывается каждый кадр: останавливает запись по таймеру.</summary>
        public static string? Tick()
        {
            if (!Active || UnityEngine.Time.unscaledTime < _until)
                return null;
            return Stop();
        }

        public static string Stop()
        {
            if (!Active)
                return "Запись не шла.";
            try { _harmony?.UnpatchSelf(); }
            catch (Exception ex) { Plugin.Logger.LogWarning("Снятие перехватчиков: " + ex.Message); }
            var parts = new List<string>();
            foreach (var kv in Counts)
                parts.Add($"{kv.Key} {kv.Value}");
            _out!.WriteLine("# counts: " + string.Join(", ", parts));
            _out.Flush();
            _out.Dispose();
            _out = null;
            return $"Запись обмена сохранена ({string.Join(", ", parts)}).";
        }

        private static void Write(string kind, string line)
        {
            Counts[kind] = Counts.TryGetValue(kind, out var n) ? n + 1 : 1;
            if (_out == null || _lines >= MaxLines)
                return;
            _lines++;
            _out.Write(UnityEngine.Time.frameCount);
            _out.Write(' ');
            _out.Write(kind);
            _out.Write(' ');
            _out.WriteLine(line);
            if ((_lines & 255) == 0)
                _out.Flush();
        }

        private static string RefName(uint id)
        {
            try
            {
                var set = ReferenceIdentifierSet.Instance.m_idToInfo;
                if (set.ContainsKey(id))
                    return set[id].Name;
            }
            catch
            {
            }
            return id.ToString();
        }

        private static string PropName(uint id)
        {
            try
            {
                var set = PropertyIdentifierSet.Instance.m_idToInfo;
                if (set.ContainsKey(id))
                    return set[id].Name;
            }
            catch
            {
            }
            return "#" + id;
        }

        private static string Ref(InteropReference? r)
        {
            if (r == null)
                return "null";
            var sb = new StringBuilder("{");
            try
            {
                sb.Append(RefName(r.ID.ID));
                var ids = r.m_id;
                for (var i = 0; ids != null && i < ids.Count; i++)
                {
                    var p = ids[i];
                    sb.Append(' ').Append(p.ID).Append('=').Append(p.Value);
                }
            }
            catch (Exception ex)
            {
                sb.Append(" !").Append(ex.Message);
            }
            return sb.Append('}').ToString();
        }

        private static string Val(TypedValue? v)
        {
            if (v == null)
                return "null";
            try
            {
                if (v.IsNull)
                    return "null";
                var s = v.AsString();
                return s == null ? "?" : (s.Length > 120 ? s.Substring(0, 120) + "…" : s);
            }
            catch
            {
                return "?";
            }
        }

        [HarmonyPatch]
        private static class Patches
        {
            [HarmonyPostfix]
            [HarmonyPatch(typeof(GameInteropSubsystem), nameof(GameInteropSubsystem.OpenChannel))]
            private static void OpenChannel(InteropReference reference, PropertyID identifier, Bindings.Key key, uint __result)
            {
                if (Active)
                    Write("OPEN", $"key={key.m_key} gen={__result} ref={Ref(reference)} prop={PropName(identifier.ID)}");
            }

            [HarmonyPostfix]
            [HarmonyPatch(typeof(GameInteropSubsystem), nameof(GameInteropSubsystem.AddNode))]
            private static void AddNode(Bindings.Key key, Bindings.Key parentKey, PropertyID property)
            {
                if (Active)
                    Write("NODE", $"key={key.m_key} parent={parentKey.m_key} prop={PropName(property.ID)}");
            }

            [HarmonyPostfix]
            [HarmonyPatch(typeof(GameInteropSubsystem), nameof(GameInteropSubsystem.SetTarget))]
            private static void SetTarget(Bindings.Key key, Bindings.DataKey targetKey)
            {
                if (Active)
                    Write("TARGET", $"key={key.m_key} data={targetKey.m_key}");
            }

            [HarmonyPostfix]
            [HarmonyPatch(typeof(GameInteropSubsystem), nameof(GameInteropSubsystem.CloseChannel))]
            private static void CloseChannel(Bindings.Key key)
            {
                if (Active)
                    Write("CLOSE", $"key={key.m_key}");
            }

            [HarmonyPostfix]
            [HarmonyPatch(typeof(GameInteropSubsystem), nameof(GameInteropSubsystem.SendEvent))]
            private static void SendEvent(uint eventID, InteropReference objectTo, TypedValue data)
            {
                if (Active)
                    Write("EVENT", $"id={eventID} to={Ref(objectTo)} data={Val(data)}");
            }
        }
    }
}
