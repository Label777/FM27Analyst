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
            var dir = Path.Combine(BepInEx.Paths.PluginPath, "FM27AnalystBridge");
            Directory.CreateDirectory(dir);
            var file = Path.Combine(dir, "engine-registry.txt");
            // Пишем по ходу (AutoFlush): если движок всё же уронит игру, в файле будет видно, на каком типе.
            using var sb = new StreamWriter(file, false, new UTF8Encoding(false)) { AutoFlush = true };
            var refsTotal = 0;
            var propsTotal = 0;
            var errors = 0;
            sb.WriteLine($"# FM27 engine registry — {DateTime.Now:yyyy-MM-dd HH:mm:ss}, game {UnityEngine.Application.version}");

            var refs = ReferenceIdentifierSet.Instance;
            var ordered = new List<(uint id, ReferenceIDInfo info)>();
            foreach (var kv in refs.m_idToInfo)
                ordered.Add((kv.Key, kv.Value));
            ordered.Sort((a, b) => string.CompareOrdinal(SafeName(a.info), SafeName(b.info)));

            foreach (var (id, info) in ordered)
            {
                refsTotal++;
                // Функции справочника — указатели в нативный код. Пустой указатель вызывать нельзя:
                // это AccessViolation, который .NET не перехватывает (игра закрывается).
                IntPtr fInstance = IntPtr.Zero, fProps = IntPtr.Zero, fType = IntPtr.Zero;
                try { fInstance = info.GetInstanceFunc; fProps = info.GetPropertiesFunc; fType = info.GetPropertyTypeFunc; }
                catch { }
                sb.WriteLine($"\nREF {id} {SafeName(info)}{(fInstance != IntPtr.Zero ? " [instance]" : "")}" +
                             $"{(fProps == IntPtr.Zero ? " [no-props-func]" : "")}{(fType == IntPtr.Zero ? " [no-type-func]" : "")}");
                if (fProps == IntPtr.Zero)
                    continue;
                var list = new Il2CppSystem.Collections.Generic.List<PropertyID>();
                try
                {
                    info.GetProperties(list);
                }
                catch (Exception ex)
                {
                    errors++;
                    sb.WriteLine("  ! GetProperties: " + ex.Message);
                    continue;
                }
                var lines = new List<string>();
                foreach (var p in list)
                {
                    propsTotal++;
                    try
                    {
                        var name = IdentifierUtils.GetName<PropertyID>(p);
                        if (fType == IntPtr.Zero)
                        {
                            lines.Add($"  {name}");
                            continue;
                        }
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
                    sb.WriteLine(l);
            }

            var props = PropertyIdentifierSet.Instance;
            sb.WriteLine($"\n# all property names: {props.m_idToInfo.Count}");
            foreach (var kv in props.m_idToInfo)
            {
                try { sb.WriteLine($"P {kv.Key} {kv.Value.Name}"); }
                catch { }
            }
            sb.WriteLine("# done");

            summary = $"типов: {refsTotal}, свойств: {propsTotal}, ошибок: {errors}";
            return file;
        }

        private static string SafeName(ReferenceIDInfo info)
        {
            try { return info.Name ?? "?"; }
            catch { return "?"; }
        }
    }
}
