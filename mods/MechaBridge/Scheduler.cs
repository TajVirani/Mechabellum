using System.Collections.Concurrent;
using System.Diagnostics;
using MechaBridge.Protocol;
using MelonLoader;

namespace MechaBridge;

/// <summary>
/// Runs requests one at a time on Unity's main thread. A job is an iterator stepped once per frame:
/// it yields null while waiting and yields its reply when done.
/// </summary>
internal sealed class Scheduler
{
    private readonly ConcurrentQueue<(Connection Connection, Envelope Request)> _queue = new();
    private readonly MelonLogger.Instance _log;
    private readonly Stopwatch _sinceServerRequest = Stopwatch.StartNew();
    private (Connection Connection, ulong Id, IEnumerator<Envelope?> Job)? _current;
    private bool _sentServerRequest;

    public Scheduler(MelonLogger.Instance log, int serverRequestIntervalMs)
    {
        _log = log;
        ServerRequestIntervalMs = serverRequestIntervalMs;
    }

    public int ServerRequestIntervalMs { get; }

    public void Enqueue(Connection connection, Envelope request) => _queue.Enqueue((connection, request));

    public void Tick()
    {
        if (_current is null)
        {
            if (!_queue.TryDequeue(out var next))
                return;
            _current = (next.Connection, next.Request.Id, Jobs.Create(this, next.Request));
        }
        var (connection, id, job) = _current.Value;
        Envelope? reply;
        try
        {
            reply = job.MoveNext() ? job.Current : Replies.Error(id, "game_error", "the request ended without a reply");
        }
        catch (BridgeException error)
        {
            reply = Replies.Error(id, error.Code, error.Message);
        }
        catch (Exception error)
        {
            _log.Warning($"Request {id} failed: {error}");
            reply = Replies.Error(id, "game_error", error.Message);
        }
        if (reply is null)
            return;
        reply.Id = id;
        job.Dispose();
        _current = null;
        _ = connection.Send(reply);
    }

    /// <summary>Waits until the pacing interval has passed since the last request sent to the game's servers.</summary>
    public IEnumerable<Envelope?> WaitForServerSlot()
    {
        while (_sentServerRequest && _sinceServerRequest.ElapsedMilliseconds < ServerRequestIntervalMs)
            yield return null;
        _sentServerRequest = true;
        _sinceServerRequest.Restart();
    }

    public static IEnumerable<Envelope?> WaitUntil(Func<bool> done, double seconds, string what)
    {
        var elapsed = Stopwatch.StartNew();
        while (!done())
        {
            if (elapsed.Elapsed.TotalSeconds > seconds)
                throw new BridgeException("timeout", $"{what} did not finish within {seconds:0} s");
            yield return null;
        }
    }
}

internal sealed class BridgeException : Exception
{
    public BridgeException(string code, string message) : base(message) => Code = code;

    public string Code { get; }
}

internal static class Replies
{
    public static Envelope Error(ulong id, string code, string message) =>
        new() { Id = id, Error = new Error { Code = code, Message = message } };
}
