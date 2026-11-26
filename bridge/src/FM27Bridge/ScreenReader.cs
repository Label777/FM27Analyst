using System;
using System.Collections.Generic;
using System.Diagnostics;
using FM27Bridge.Core;
using FM27Exporter;
using FM27Exporter.Core;
using UnityEngine.UIElements;

namespace FM27Bridge
{
    /// <summary>Читает все видимые тексты интерфейса — то, что игрок видит на экране, не больше.</summary>
    internal static class ScreenReader
    {
        private static readonly string[] ScreenSuffixes = { "MainContentBlock", "ContentBlock", "Screen" };

        public static ScreenPayload Read(int maxTexts, out long elapsedMs)
        {
            var clock = Stopwatch.StartNew();
            var texts = new List<ScreenText>();
            float width = 0, height = 0;
            string screen = "";
            var screenArea = 0f;
            foreach (var root in Ui.PanelRoots())
            {
                try
                {
                    var b = root.worldBound;
                    width = Math.Max(width, b.width);
                    height = Math.Max(height, b.height);
                }
                catch
                {
                }
                Ui.Walk(root, e =>
                {
                    if (texts.Count > maxTexts * 2)
                        return false;
                    if (Ui.IsHidden(e))
                        return false;
                    var name = e.name;
                    if (!string.IsNullOrEmpty(name))
                    {
                        foreach (var suffix in ScreenSuffixes)
                        {
                            if (name!.Length > suffix.Length && name.EndsWith(suffix, StringComparison.Ordinal))
                            {
                                var area = Ui.Area(e);
                                if (area > screenArea)
                                {
                                    screenArea = area;
                                    screen = ExportNames.Words(name.Substring(0, name.Length - suffix.Length));
                                }
                                break;
                            }
                        }
                    }
                    var text = Ui.AsText(e)?.text;
                    if (!string.IsNullOrEmpty(text))
                    {
                        var r = e.worldBound;
                        if (r.width > 0 && r.height > 0)
                            texts.Add(new ScreenText
                            {
                                Text = text!,
                                Path = Diagnostics.Path(e),
                                Classes = string.Join(" ", FirstClasses(e, 4)),
                                X = r.x, Y = r.y, W = r.width, H = r.height,
                            });
                        return false; // части метки (иконки внутри текста) не нужны
                    }
                    return true;
                });
            }
            var payload = ScreenDump.Build(texts, maxTexts, screen, width, height);
            elapsedMs = clock.ElapsedMilliseconds;
            return payload;
        }

        private static List<string> FirstClasses(VisualElement e, int max)
        {
            var all = Ui.Classes(e);
            return all.Count <= max ? all : all.GetRange(0, max);
        }
    }
}
