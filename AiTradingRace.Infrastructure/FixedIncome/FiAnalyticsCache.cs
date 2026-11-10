using System.Text.Json.Nodes;

namespace AiTradingRace.Infrastructure.FixedIncome;

/// <summary>
/// Bounded in-memory cache of research-engine analytics documents (evaluation metrics,
/// payment calendars). Keys embed the committed portfolio versions and decision counts the
/// result was computed from, so a new commit naturally misses; entries are immutable inputs'
/// outputs and never need invalidation. Values are deep-cloned in and out so callers can
/// attach them to response graphs.
/// </summary>
public sealed class FiAnalyticsCache
{
    public const int DefaultCapacity = 512;

    private readonly object _gate = new();
    private readonly Dictionary<string, JsonNode> _items = new(StringComparer.Ordinal);
    private readonly Queue<string> _order = new();
    private readonly int _capacity;

    public FiAnalyticsCache() : this(DefaultCapacity)
    {
    }

    public FiAnalyticsCache(int capacity)
    {
        _capacity = Math.Max(1, capacity);
    }

    public int Count
    {
        get
        {
            lock (_gate)
            {
                return _items.Count;
            }
        }
    }

    public bool TryGet(string key, out JsonNode? value)
    {
        lock (_gate)
        {
            if (_items.TryGetValue(key, out var hit))
            {
                value = hit.DeepClone();
                return true;
            }
        }

        value = null;
        return false;
    }

    public void Set(string key, JsonNode value)
    {
        var copy = value.DeepClone();
        lock (_gate)
        {
            if (!_items.ContainsKey(key))
            {
                _order.Enqueue(key);
            }

            _items[key] = copy;
            while (_items.Count > _capacity && _order.Count > 0)
            {
                _items.Remove(_order.Dequeue());
            }
        }
    }
}
