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

        // Ответы движка и проба собственного запроса
        private static GameInteropSubsystem? _subsystem;
        private static ValueChangedWithSizeCallback? _callback;
        private static List<(uint id, int value)>? _lastPerson;
        private static bool _probePending;
        private static float _probeCloseAt;
        private static readonly HashSet<ulong> MyKeys = new HashSet<ulong>();
        private static readonly Dictionary<ulong, string> MyKeyNames = new Dictionary<ulong, string>();
        private static readonly List<ulong> MyChannels = new List<ulong>();
        private static readonly List<ulong> MyNodes = new List<ulong>();
        private static ulong _nextKey = 0xFA27_0000_0000_0001UL;
        private static Dictionary<string, uint>? _propByName;
        private static int _dataLines;

        public static bool Active => _out != null;
        public static string? File { get; private set; }

        public static string StartProbe(float seconds)
        {
            var r = Start(seconds);
            _probePending = true;
            return "Проба запроса к движку: откройте в игре профиль любого игрока (вкладка атрибутов). " + r;
        }

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
            _dataLines = 0;
            Counts.Clear();
            _probePending = false;
            _probeCloseAt = 0;
            _until = UnityEngine.Time.unscaledTime + seconds;
            _harmony ??= new Harmony(Plugin.Guid + ".sniff");
            _harmony.PatchAll(typeof(Patches));
            return $"Запись обмена с движком: {seconds:0} с. Откройте в игре профиль игрока и вкладку атрибутов.";
        }

        /// <summary>Вызывается каждый кадр: останавливает запись по таймеру.</summary>
        public static string? Tick()
        {
            if (!Active)
                return null;
            try
            {
                if (_probePending && _subsystem != null && _lastPerson != null)
                {
                    _probePending = false;
                    RunProbe();
                }
                if (_probeCloseAt > 0 && UnityEngine.Time.unscaledTime >= _probeCloseAt)
                {
                    _probeCloseAt = 0;
                    CloseProbe();
                }
            }
            catch (Exception ex)
            {
                Write("PROBE", "! " + ex);
            }
            if (UnityEngine.Time.unscaledTime < _until)
                return null;
            return Stop();
        }

        private static uint Prop(string name)
        {
            if (_propByName == null)
            {
                _propByName = new Dictionary<string, uint>();
                foreach (var kv in PropertyIdentifierSet.Instance.m_idToInfo)
                {
                    try { _propByName[kv.Value.Name] = kv.Key; }
                    catch { }
                }
            }
            return _propByName.TryGetValue(name, out var id) ? id : 0;
        }

        private static ulong NewKey(string label)
        {
            var k = _nextKey++;
            MyKeys.Add(k);
            MyKeyNames[k] = label;
            return k;
        }

        /// <summary>Свой запрос к движку: несколько свойств последнего игрока, которого показал интерфейс.</summary>
        private static void RunProbe()
        {
            var pairs = new Il2CppSystem.Collections.Generic.List<InteropReference.Pair>();
            foreach (var (id, value) in _lastPerson!)
                pairs.Add(new InteropReference.Pair(id, value));
            var reference = new InteropReference(pairs);
            Write("PROBE", "person " + Ref(reference));

            void Open(string prop, params string[] children)
            {
                var pid = Prop(prop);
                if (pid == 0)
                {
                    Write("PROBE", $"нет свойства {prop}");
                    return;
                }
                var key = NewKey(prop);
                var gen = _subsystem!.OpenChannel(reference, new PropertyID(pid), new Bindings.Key(key));
                MyChannels.Add(key);
                Write("PROBE", $"open {prop} key={key} gen={gen}");
                foreach (var c in children)
                {
                    var cid = Prop(c);
                    if (cid == 0)
                        continue;
                    var ck = NewKey(prop + "." + c);
                    _subsystem.AddNode(new Bindings.Key(ck), new Bindings.Key(key), new PropertyID(cid));
                    MyNodes.Add(ck);
                    Write("PROBE", $"node {prop}.{c} key={ck}");
                }
            }

            Open("Name");
            Open("Age");
            Open("UniqueId");
            Open("AttributeFinishing", "AttributeMinValue", "AttributeMaxValue", "PropertyValue");
            Open("AttributeDetermination", "AttributeMinValue", "AttributeMaxValue", "PropertyValue");
            Open("CurrentAbilityStarRange", "MinValue", "MaxValue", "IsScoutsOpinion");
            Open("DebugCalculatedPerceivedPotential");
            Open("AbilityCentreBack");
            _probeCloseAt = UnityEngine.Time.unscaledTime + 8f;
        }

        private static void CloseProbe()
        {
            if (_subsystem == null)
                return;
            foreach (var k in MyNodes)
            {
                try { _subsystem.RemoveNode(new Bindings.Key(k)); } catch { }
            }
            foreach (var k in MyChannels)
            {
                try { _subsystem.CloseChannel(new Bindings.Key(k)); } catch { }
            }
            Write("PROBE", $"closed {MyChannels.Count} channels, {MyNodes.Count} nodes");
            MyNodes.Clear();
            MyChannels.Clear();
        }

        private static void Subscribe(GameInteropSubsystem g)
        {
            if (_subsystem != null)
                return;
            _subsystem = g;
            _callback ??= Il2CppInterop.Runtime.DelegateSupport.ConvertDelegate<ValueChangedWithSizeCallback>(
                new Action<Il2CppSystem.ReadOnlySpan<ulong>, Il2CppSystem.ReadOnlySpan<uint>,
                    Il2CppSystem.Collections.Generic.List<TypedValue>, Il2CppSystem.ReadOnlySpan<long>>(OnData));
            g.add_OnChannelDataChange(_callback);
            Write("INFO", "subscribed to channel data");
        }

        private static void OnData(Il2CppSystem.ReadOnlySpan<ulong> keys, Il2CppSystem.ReadOnlySpan<uint> gens,
            Il2CppSystem.Collections.Generic.List<TypedValue> values, Il2CppSystem.ReadOnlySpan<long> sizes)
        {
            if (!Active)
                return;
            try
            {
                var n = keys.Length;
                for (var i = 0; i < n; i++)
                {
                    var k = keys[i];
                    var mine = MyKeys.Contains(k);
                    if (!mine && _dataLines > 15000)
                        continue;
                    _dataLines++;
                    var v = values != null && i < values.Count ? values[i] : null;
                    string type;
                    try { type = v?.DataType?.FullName ?? "-"; } catch { type = "?"; }
                    var label = mine ? " MY " + MyKeyNames[k] : "";
                    Write(mine ? "MYDATA" : "DATA", $"key={k} gen={(i < gens.Length ? gens[i] : 0)} n={n}{label} type={type} val={Val(v)}");
                }
            }
            catch (Exception ex)
            {
                Write("DATA", "! " + ex.Message);
            }
        }

        public static string Stop()
        {
            if (!Active)
                return "Запись не шла.";
            try
            {
                if (MyChannels.Count > 0)
                    CloseProbe();
                if (_subsystem != null && _callback != null)
                    _subsystem.remove_OnChannelDataChange(_callback);
            }
            catch (Exception ex) { Plugin.Logger.LogWarning("Отписка: " + ex.Message); }
            _subsystem = null;
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
            private static void OpenChannel(GameInteropSubsystem __instance, InteropReference reference, PropertyID identifier, Bindings.Key key, uint __result)
            {
                if (!Active || MyKeys.Contains(key.m_key))
                    return;
                Subscribe(__instance);
                Write("OPEN", $"key={key.m_key} gen={__result} ref={Ref(reference)} prop={PropName(identifier.ID)}");
                try
                {
                    if (reference != null && RefName(reference.ID.ID) == "person")
                    {
                        var list = new List<(uint, int)>();
                        var ids = reference.m_id;
                        for (var i = 0; i < ids.Count; i++)
                            list.Add((ids[i].ID, ids[i].Value));
                        _lastPerson = list;
                    }
                }
                catch
                {
                }
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
