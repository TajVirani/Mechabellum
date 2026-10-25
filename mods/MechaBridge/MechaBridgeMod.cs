using MelonLoader;

[assembly: MelonInfo(typeof(MechaBridge.MechaBridgeMod), "MechaBridge", "0.2.0", "taj")]
[assembly: MelonGame("GameRiver", "Mechabellum")]

namespace MechaBridge;

/// <summary>
/// Serves the bridge protocol (contracts/bridge/v1/bridge.proto) on a local WebSocket.
/// Requests are queued by the server's network threads and executed one at a time on Unity's main thread.
/// </summary>
public sealed class MechaBridgeMod : MelonMod
{
    private MelonPreferences_Entry<int> _port = null!;
    private MelonPreferences_Entry<int> _serverRequestIntervalMs = null!;
    private BridgeServer? _server;
    private Scheduler? _scheduler;

    public override void OnInitializeMelon()
    {
        var category = MelonPreferences.CreateCategory("MechaBridge");
        _port = category.CreateEntry("Port", 17615, description: "Local WebSocket port.");
        _serverRequestIntervalMs = category.CreateEntry(
            "ServerRequestIntervalMs", 1500, description: "Minimum time between requests sent to the game's servers.");

        _scheduler = new Scheduler(LoggerInstance, Math.Max(_serverRequestIntervalMs.Value, 500));
        _server = new BridgeServer(_port.Value, _scheduler, LoggerInstance);
        _server.Start();
    }

    public override void OnUpdate() => _scheduler?.Tick();

    public override void OnApplicationQuit() => _server?.Stop();
}
