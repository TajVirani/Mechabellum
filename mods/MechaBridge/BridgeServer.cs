using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using Google.Protobuf;
using MechaBridge.Protocol;
using MelonLoader;

namespace MechaBridge;

/// <summary>
/// Minimal WebSocket server on the loopback interface. A raw TcpListener avoids http.sys URL reservations.
/// </summary>
internal sealed class BridgeServer
{
    private const string HandshakeGuid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    private const int MaxMessageBytes = 1 << 20;

    private readonly int _port;
    private readonly Scheduler _scheduler;
    private readonly MelonLogger.Instance _log;
    private readonly CancellationTokenSource _stopping = new();
    private TcpListener? _listener;

    public BridgeServer(int port, Scheduler scheduler, MelonLogger.Instance log)
    {
        _port = port;
        _scheduler = scheduler;
        _log = log;
    }

    public void Start()
    {
        _listener = new TcpListener(IPAddress.Loopback, _port);
        _listener.Start();
        _log.Msg($"Listening on ws://127.0.0.1:{_port}/");
        _ = Task.Run(AcceptLoop);
    }

    public void Stop()
    {
        _stopping.Cancel();
        _listener?.Stop();
    }

    private async Task AcceptLoop()
    {
        while (!_stopping.IsCancellationRequested)
        {
            TcpClient client;
            try
            {
                client = await _listener!.AcceptTcpClientAsync(_stopping.Token);
            }
            catch (Exception) when (_stopping.IsCancellationRequested)
            {
                return;
            }
            _ = Task.Run(() => Serve(client));
        }
    }

    private async Task Serve(TcpClient client)
    {
        using var _ = client;
        client.NoDelay = true;
        var stream = client.GetStream();
        try
        {
            if (!await Handshake(stream))
                return;
            using var socket = WebSocket.CreateFromStream(stream, isServer: true, subProtocol: null, TimeSpan.FromSeconds(30));
            var connection = new Connection(socket);
            await ReceiveLoop(connection);
        }
        catch (Exception error) when (error is IOException or WebSocketException or OperationCanceledException)
        {
            // The client went away.
        }
        catch (Exception error)
        {
            _log.Warning($"Connection failed: {error}");
        }
    }

    /// <summary>Accepts an RFC 6455 upgrade request. Browsers may connect only from local pages.</summary>
    private static async Task<bool> Handshake(NetworkStream stream)
    {
        var request = await ReadHeaders(stream);
        if (request is null)
            return false;
        var headers = request.Split("\r\n")
            .Skip(1)
            .Select(line => line.Split(':', 2))
            .Where(parts => parts.Length == 2)
            .GroupBy(parts => parts[0].Trim(), StringComparer.OrdinalIgnoreCase)
            .ToDictionary(group => group.Key, group => group.First()[1].Trim(), StringComparer.OrdinalIgnoreCase);
        if (!headers.TryGetValue("Sec-WebSocket-Key", out var key) || !IsLocalOrigin(headers))
        {
            await stream.WriteAsync(Encoding.ASCII.GetBytes("HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"));
            return false;
        }
        var accept = Convert.ToBase64String(SHA1.HashData(Encoding.ASCII.GetBytes(key + HandshakeGuid)));
        var response = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" +
                       $"Sec-WebSocket-Accept: {accept}\r\n\r\n";
        await stream.WriteAsync(Encoding.ASCII.GetBytes(response));
        return true;
    }

    private static bool IsLocalOrigin(Dictionary<string, string> headers)
    {
        // Non-browser clients send no Origin; any website the user visits could otherwise drive the game.
        if (!headers.TryGetValue("Origin", out var origin) || origin == "null")
            return true;
        return Uri.TryCreate(origin, UriKind.Absolute, out var uri) && (uri.IsLoopback || uri.Host == "localhost");
    }

    private static async Task<string?> ReadHeaders(NetworkStream stream)
    {
        var buffer = new List<byte>();
        var one = new byte[1];
        while (buffer.Count < 16 * 1024)
        {
            if (await stream.ReadAsync(one) == 0)
                return null;
            buffer.Add(one[0]);
            var count = buffer.Count;
            if (count >= 4 && buffer[count - 4] == '\r' && buffer[count - 3] == '\n' && buffer[count - 2] == '\r' && buffer[count - 1] == '\n')
                return Encoding.ASCII.GetString(buffer.ToArray());
        }
        return null;
    }

    private async Task ReceiveLoop(Connection connection)
    {
        var buffer = new byte[64 * 1024];
        var message = new MemoryStream();
        while (connection.Socket.State == WebSocketState.Open && !_stopping.IsCancellationRequested)
        {
            var result = await connection.Socket.ReceiveAsync(buffer, _stopping.Token);
            if (result.MessageType == WebSocketMessageType.Close)
            {
                await connection.Socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, null, CancellationToken.None);
                return;
            }
            message.Write(buffer, 0, result.Count);
            if (message.Length > MaxMessageBytes)
            {
                await connection.Socket.CloseOutputAsync(WebSocketCloseStatus.MessageTooBig, null, CancellationToken.None);
                return;
            }
            if (!result.EndOfMessage)
                continue;
            if (result.MessageType == WebSocketMessageType.Binary)
            {
                Envelope envelope;
                try
                {
                    envelope = Envelope.Parser.ParseFrom(message.ToArray());
                }
                catch (InvalidProtocolBufferException error)
                {
                    await connection.Send(Replies.Error(0, "invalid_request", error.Message));
                    message.SetLength(0);
                    continue;
                }
                _scheduler.Enqueue(connection, envelope);
            }
            message.SetLength(0);
        }
    }
}

internal sealed class Connection
{
    private readonly SemaphoreSlim _sending = new(1, 1);

    public Connection(WebSocket socket) => Socket = socket;

    public WebSocket Socket { get; }

    public async Task Send(Envelope envelope)
    {
        var bytes = envelope.ToByteArray();
        await _sending.WaitAsync();
        try
        {
            if (Socket.State == WebSocketState.Open)
                await Socket.SendAsync(bytes, WebSocketMessageType.Binary, endOfMessage: true, CancellationToken.None);
        }
        finally
        {
            _sending.Release();
        }
    }
}
