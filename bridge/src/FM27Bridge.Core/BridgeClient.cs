using System;
using System.Collections.Concurrent;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace FM27Bridge.Core
{
    public interface ITransport
    {
        // null — ядро недоступно
        string? Get(string path);
        bool Post(string path, string json);
        // Причина последней неудачи — для журнала BepInEx
        string? LastError { get; }
    }

    public sealed class HttpTransport : ITransport, IDisposable
    {
        private readonly HttpClient _http;

        public string? LastError { get; private set; }

        public HttpTransport(string baseUrl, TimeSpan timeout)
        {
            // Ядро на этом же компьютере: системный прокси/VPN не нужен и может мешать.
            var handler = new HttpClientHandler { UseProxy = false };
            _http = new HttpClient(handler) { BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/"), Timeout = timeout };
        }

        private static string Describe(Exception ex)
        {
            var e = ex;
            var parts = new System.Collections.Generic.List<string>();
            while (e != null && parts.Count < 4)
            {
                parts.Add($"{e.GetType().Name}: {e.Message}");
                e = e.InnerException;
            }
            return string.Join(" → ", parts);
        }

        public string? Get(string path)
        {
            try
            {
                var r = _http.GetAsync(path.TrimStart('/')).GetAwaiter().GetResult();
                if (!r.IsSuccessStatusCode)
                {
                    LastError = $"GET {path}: HTTP {(int)r.StatusCode}";
                    return null;
                }
                LastError = null;
                return r.Content.ReadAsStringAsync().GetAwaiter().GetResult();
            }
            catch (Exception ex)
            {
                LastError = $"GET {path}: {Describe(ex)}";
                return null;
            }
        }

        public bool Post(string path, string json)
        {
            try
            {
                using var content = new StringContent(json, Encoding.UTF8, "application/json");
                var r = _http.PostAsync(path.TrimStart('/'), content).GetAwaiter().GetResult();
                if (!r.IsSuccessStatusCode)
                {
                    var body = r.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                    LastError = $"POST {path}: HTTP {(int)r.StatusCode} {(body.Length > 300 ? body.Substring(0, 300) : body)}";
                    return false;
                }
                LastError = null;
                return true;
            }
            catch (Exception ex)
            {
                LastError = $"POST {path}: {Describe(ex)}";
                return false;
            }
        }

        public void Dispose() => _http.Dispose();
    }

    /// <summary>
    /// Связь с ядром в фоновом потоке. Поток не трогает объекты игры: он только кладёт команды
    /// в очередь, а главный поток Unity забирает их в Update() и отвечает через Send().
    /// </summary>
    public sealed class BridgeClient : IDisposable
    {
        public static readonly JsonSerializerOptions Json = new JsonSerializerOptions
        {
            DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull,
        };

        private readonly ITransport _transport;
        private readonly Hello _hello;
        private readonly Action<string>? _log;
        private readonly ConcurrentQueue<Command> _commands = new ConcurrentQueue<Command>();
        private readonly ConcurrentQueue<(string path, string json)> _outbox = new ConcurrentQueue<(string, string)>();
        private readonly AutoResetEvent _wake = new AutoResetEvent(false);
        private Thread? _thread;
        private volatile bool _stop;
        private bool _helloSent;

        public BridgeClient(ITransport transport, Hello hello, Action<string>? log = null)
        {
            _transport = transport;
            _hello = hello;
            _log = log;
        }

        public TimeSpan PollInterval { get; set; } = TimeSpan.FromSeconds(1);
        public TimeSpan OfflineInterval { get; set; } = TimeSpan.FromSeconds(5);
        public int MaxOutbox { get; set; } = 20;

        public volatile bool Connected;
        public volatile bool AutoScreen;
        public double AutoIntervalSec = 3;

        public void Start()
        {
            if (_thread != null)
                return;
            _thread = new Thread(Loop) { IsBackground = true, Name = "FM27 Analyst Bridge" };
            _thread.Start();
        }

        public bool TryNextCommand(out Command command) => _commands.TryDequeue(out command!);

        public void Send(string path, object payload)
        {
            while (_outbox.Count >= MaxOutbox && _outbox.TryDequeue(out _))
            {
                // старые снимки теряют смысл: оставляем свежие
            }
            _outbox.Enqueue((path, JsonSerializer.Serialize(payload, payload.GetType(), Json)));
            _wake.Set();
        }

        /// <summary>Один цикл обмена. Публичный — для тестов без потоков.</summary>
        public void Step()
        {
            if (!_helloSent)
            {
                _helloSent = _transport.Post("api/bridge/hello", JsonSerializer.Serialize(_hello, Json));
                if (!_helloSent)
                {
                    SetConnected(false);
                    return;
                }
            }
            var reply = _transport.Get("api/bridge/poll");
            if (reply == null)
            {
                SetConnected(false);
                _helloSent = false; // ядро могли перезапустить — представимся заново
                return;
            }
            SetConnected(true);
            try
            {
                var poll = JsonSerializer.Deserialize<PollReply>(reply, Json);
                if (poll != null)
                {
                    AutoScreen = poll.AutoScreen;
                    AutoIntervalSec = Math.Max(1, poll.AutoIntervalSec);
                    foreach (var c in poll.Commands)
                        _commands.Enqueue(c);
                }
            }
            catch (JsonException ex)
            {
                _log?.Invoke("Ответ ядра не разобран: " + ex.Message);
            }
            while (_outbox.TryPeek(out var item))
            {
                if (!_transport.Post(item.path, item.json))
                {
                    SetConnected(false);
                    return; // отправим в следующий раз
                }
                _outbox.TryDequeue(out _);
            }
        }

        private string? _lastLoggedError;
        private DateTime _lastErrorLogAt = DateTime.MinValue;

        private void SetConnected(bool value)
        {
            if (Connected != value)
                _log?.Invoke(value ? "Связь с FM27 Analyst установлена." : "FM27 Analyst не отвечает — жду.");
            if (!value)
            {
                // Причину пишем сразу при первой неудаче и при её смене, иначе — не чаще раза в минуту.
                var err = _transport.LastError ?? "нет ответа";
                if (err != _lastLoggedError || DateTime.UtcNow - _lastErrorLogAt > TimeSpan.FromMinutes(1))
                {
                    _log?.Invoke("Нет связи с FM27 Analyst: " + err);
                    _lastLoggedError = err;
                    _lastErrorLogAt = DateTime.UtcNow;
                }
            }
            else
                _lastLoggedError = null;
            Connected = value;
        }

        private void Loop()
        {
            while (!_stop)
            {
                try
                {
                    Step();
                }
                catch (Exception ex)
                {
                    _log?.Invoke("Ошибка связи: " + ex.Message);
                    Connected = false;
                }
                _wake.WaitOne(Connected ? PollInterval : OfflineInterval);
            }
        }

        public void Dispose()
        {
            _stop = true;
            _wake.Set();
        }
    }
}
