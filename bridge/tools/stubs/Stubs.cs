// Заглушки API BepInEx / Il2CppInterop / Unity — ТОЛЬКО для проверки компиляции моста без игры.
// В плагин не входят: настоящая сборка идёт против файлов из папки BepInEx установленной игры.
#pragma warning disable CS8618, CS0067, CS1591
using System;
using System.Collections.Generic;

namespace Il2CppInterop.Runtime.InteropTypes
{
    public class Il2CppObjectBase
    {
        public IntPtr Pointer => IntPtr.Zero;
        public T? TryCast<T>() where T : Il2CppObjectBase => null;
    }
}

namespace Il2CppInterop.Runtime
{
    public static class IL2CPP
    {
        public static IntPtr il2cpp_object_get_class(IntPtr o) => o;
        public static IntPtr il2cpp_class_get_namespace(IntPtr k) => k;
        public static IntPtr il2cpp_class_get_name(IntPtr k) => k;
        public static IntPtr il2cpp_class_get_parent(IntPtr k) => k;
        public static IntPtr il2cpp_class_get_method_from_name(IntPtr k, string n, int argc) => k;
        public static unsafe IntPtr il2cpp_runtime_invoke(IntPtr m, IntPtr o, void** args, ref IntPtr exc) => m;
        public static IntPtr il2cpp_object_unbox(IntPtr o) => o;
    }

    public static class Il2CppType
    {
        public static Il2CppSystem.Type Of<T>() => new Il2CppSystem.Type();
    }
}

namespace Il2CppSystem
{
    public class Type { }

    namespace Collections.Generic
    {
        public class List<T> : Il2CppInterop.Runtime.InteropTypes.Il2CppObjectBase
        {
            public int Count => 0;
            public T this[int i] => default!;
        }
    }
}

namespace BepInEx.Logging
{
    public class ManualLogSource
    {
        public void LogInfo(object o) { }
        public void LogWarning(object o) { }
        public void LogError(object o) { }
        public void LogDebug(object o) { }
    }
}

namespace BepInEx.Configuration
{
    public class ConfigEntry<T>
    {
        public T Value { get; set; }
        public event EventHandler SettingChanged;
    }

    public class ConfigFile
    {
        public ConfigEntry<T> Bind<T>(string section, string key, T def, string description) => new ConfigEntry<T> { Value = def };
    }
}

namespace BepInEx
{
    [AttributeUsage(AttributeTargets.Class)]
    public class BepInPlugin : Attribute
    {
        public BepInPlugin(string guid, string name, string version) { }
    }
}

namespace BepInEx.Unity.IL2CPP
{
    public abstract class BasePlugin
    {
        public BepInEx.Logging.ManualLogSource Log { get; } = new BepInEx.Logging.ManualLogSource();
        public BepInEx.Configuration.ConfigFile Config { get; } = new BepInEx.Configuration.ConfigFile();
        public abstract void Load();
        public T AddComponent<T>() where T : UnityEngine.MonoBehaviour => null!;
    }
}

namespace UnityEngine
{
    public struct Vector2
    {
        public float x, y;
        public Vector2(float x, float y) { this.x = x; this.y = y; }
    }

    public struct Rect
    {
        public float x, y, width, height;
        public Rect(float x, float y, float w, float h) { this.x = x; this.y = y; width = w; height = h; }
    }

    public enum TextAnchor { MiddleCenter }

    public class Object : Il2CppInterop.Runtime.InteropTypes.Il2CppObjectBase
    {
        public static Object[] FindObjectsOfType(Il2CppSystem.Type t) => Array.Empty<Object>();
    }

    public class MonoBehaviour : Object
    {
        public MonoBehaviour(IntPtr p) { }
    }

    public static class Application
    {
        public static string version => "";
        public static string unityVersion => "";
        public static string productName => "";
        public static int targetFrameRate { get; set; }
    }

    public static class Time
    {
        public static float unscaledTime => 0;
    }

    public static class Screen
    {
        public static int width => 0;
        public static int height => 0;
    }

    public class GUIStyle
    {
        public int fontSize { get; set; }
        public bool wordWrap { get; set; }
        public TextAnchor alignment { get; set; }
    }

    public class GUISkin
    {
        public GUIStyle box => new GUIStyle();
    }

    public static class GUI
    {
        public static GUISkin skin => new GUISkin();
        public static void Box(Rect r, string text, GUIStyle style) { }
    }
}

namespace UnityEngine.UIElements
{
    public enum DisplayStyle { Flex, None }

    public interface IResolvedStyle
    {
        DisplayStyle display { get; }
    }

    public interface IPanel
    {
        VisualElement visualTree { get; }
        VisualElement Pick(Vector2 p);
    }

    public class VisualElement : Il2CppInterop.Runtime.InteropTypes.Il2CppObjectBase
    {
        public VisualElement() { }
        public VisualElement(IntPtr p) { }
        public string name { get; set; }
        public int childCount => 0;
        public VisualElement this[int i] => null!;
        public VisualElement parent => null!;
        public Rect worldBound => default;
        public Rect layout => default;
        public bool visible => true;
        public IResolvedStyle resolvedStyle => null!;
        public IPanel panel => null!;
        public bool ClassListContains(string c) => false;
        public Il2CppSystem.Collections.Generic.List<string> GetClassesForIteration() => null!;
    }

    public class TextElement : VisualElement
    {
        public TextElement(IntPtr p) : base(p) { }
        public string text { get; set; }
    }

    public class Scroller : VisualElement
    {
        public float highValue => 0;
    }

    public class ScrollView : VisualElement
    {
        public ScrollView(IntPtr p) : base(p) { }
        public Vector2 scrollOffset { get; set; }
        public VisualElement contentViewport => null!;
        public VisualElement contentContainer => null!;
        public Scroller verticalScroller => null!;
    }

    public class UIDocument : Object
    {
        public VisualElement rootVisualElement => null!;
    }

    public class Panel : IPanel
    {
        public VisualElement visualTree => null!;
        public VisualElement Pick(Vector2 p) => null!;
    }

    public static class UIElementsRuntimeUtility
    {
        public static Il2CppSystem.Collections.Generic.List<Panel> GetSortedPlayerPanels() => null!;
    }
}
