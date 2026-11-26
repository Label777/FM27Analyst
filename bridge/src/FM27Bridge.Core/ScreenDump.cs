using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

namespace FM27Bridge.Core
{
    public static class ScreenDump
    {
        /// <summary>Порядок чтения: сверху вниз, слева направо; пустые и дубли по месту — убираем.</summary>
        public static ScreenPayload Build(IEnumerable<ScreenText> raw, int maxTexts, string screen, float width, float height)
        {
            var list = new List<ScreenText>();
            var seen = new HashSet<string>();
            foreach (var t in raw)
            {
                var text = FM27Exporter.Core.CellText.Clean(t.Text);
                if (text.Length == 0)
                    continue;
                var key = $"{text}|{Math.Round(t.X)}|{Math.Round(t.Y)}";
                if (!seen.Add(key))
                    continue;
                t.Text = text.Length > 400 ? text.Substring(0, 400) + "…" : text;
                list.Add(t);
            }
            list.Sort((a, b) =>
            {
                var dy = Math.Round(a.Y / 4f).CompareTo(Math.Round(b.Y / 4f));
                return dy != 0 ? dy : a.X.CompareTo(b.X);
            });
            var truncated = list.Count > maxTexts;
            if (truncated)
                list.RemoveRange(maxTexts, list.Count - maxTexts);
            return new ScreenPayload
            {
                Screen = screen,
                Texts = list,
                Truncated = truncated,
                Width = width,
                Height = height,
                Hash = Hash(list),
            };
        }

        /// <summary>Хэш только по текстам в порядке чтения: сдвиги на пиксель и анимации изменением не считаются.</summary>
        public static string Hash(IEnumerable<ScreenText> texts)
        {
            var sb = new StringBuilder();
            foreach (var t in texts)
                sb.Append(t.Text).Append('\n');
            using var sha = SHA1.Create();
            var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(sb.ToString()));
            var hex = new StringBuilder(16);
            for (var i = 0; i < 8; i++)
                hex.Append(bytes[i].ToString("x2"));
            return hex.ToString();
        }

        /// <summary>Тексты верхней полосы экрана — там FM показывает дату, клуб, кнопку «Продолжить».</summary>
        public static List<string> TopStrip(IEnumerable<ScreenText> texts, float screenHeight, float fraction = 0.12f, int max = 40)
        {
            var result = new List<string>();
            var limit = screenHeight > 0 ? screenHeight * fraction : 120f;
            foreach (var t in texts)
            {
                if (t.Y <= limit && t.Text.Length > 0)
                    result.Add(t.Text);
                if (result.Count >= max)
                    break;
            }
            return result;
        }
    }
}
