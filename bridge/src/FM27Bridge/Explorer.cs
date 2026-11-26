using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using SI.Bindable.Reference.Core;

namespace FM27Bridge
{
    /// <summary>
    /// Разведка движка: справочник типов данных, которые движок FM27 отдаёт интерфейсу
    /// (ReferenceIdentifierSet / PropertyIdentifierSet из SI.Bindable). Только чтение справочника —
    /// значения игроков здесь не читаются. Результат — текстовый файл для разработчика.
    /// </summary>
    internal static class Explorer
    {
        public static string Run(out string summary)
        {
            var sb = new StringBuilder();
            var refsTotal = 0;
            var propsTotal = 0;
            var errors = 0;
            sb.AppendLine($"# FM27 engine registry — {DateTime.Now:yyyy-MM-dd HH:mm:ss}, game {UnityEngine.Application.version}");

            var refs = ReferenceIdentifierSet.Instance;
            var ordered = new List<(uint id, ReferenceIDInfo info)>();
            foreach (var kv in refs.m_idToInfo)
                ordered.Add((kv.Key, kv.Value));
            ordered.Sort((a, b) => string.CompareOrdinal(SafeName(a.info), SafeName(b.info)));

            foreach (var (id, info) in ordered)
            {
                refsTotal++;
                string instance;
                try { instance = info.GetInstance() != null ? " [singleton]" : ""; }
                catch { instance = ""; }
                sb.AppendLine($"\nREF {id} {SafeName(info)}{instance}");
                var list = new Il2CppSystem.Collections.Generic.List<PropertyID>();
                try
                {
                    info.GetProperties(list);
                }
                catch (Exception ex)
                {
                    errors++;
                    sb.AppendLine("  ! GetProperties: " + ex.Message);
                    continue;
                }
                var lines = new List<string>();
                foreach (var p in list)
                {
                    propsTotal++;
                    try
                    {
                        var name = IdentifierUtils.GetName<PropertyID>(p);
                        var kind = info.GetPropertyType(p);
                        var target = "";
                        try
                        {
                            if (kind.Reference != ReferenceID.Invalid)
                                target = " -> " + IdentifierUtils.GetName<ReferenceID>(kind.Reference);
                        }
                        catch
                        {
                        }
                        string type;
                        try { type = kind.Type?.FullName ?? "-"; }
                        catch { type = "?"; }
                        lines.Add($"  {name} : {kind.Kind} {type}{(kind.IsList ? "[]" : "")}{target}");
                    }
                    catch (Exception ex)
                    {
                        errors++;
                        lines.Add($"  #{p.ID} ! {ex.Message}");
                    }
                }
                lines.Sort(StringComparer.Ordinal);
                foreach (var l in lines)
                    sb.AppendLine(l);
            }

            var props = PropertyIdentifierSet.Instance;
            sb.AppendLine($"\n# all property names: {props.m_idToInfo.Count}");

            summary = $"типов: {refsTotal}, свойств: {propsTotal}, ошибок: {errors}";
            var dir = Path.Combine(BepInEx.Paths.PluginPath, "FM27AnalystBridge");
            Directory.CreateDirectory(dir);
            var file = Path.Combine(dir, "engine-registry.txt");
            File.WriteAllText(file, sb.ToString(), new UTF8Encoding(false));
            return file;
        }

        private static string SafeName(ReferenceIDInfo info)
        {
            try { return info.Name ?? "?"; }
            catch { return "?"; }
        }
    }
}
