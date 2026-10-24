using Il2CppGameRiver;
using Il2CppGameRiver.Client;
using Il2CppInterop.Runtime.InteropTypes;

namespace MechaBridge;

/// <summary>Read access to the game's services. Call only from the main thread.</summary>
internal static class Game
{
    /// <summary>Looks up a PureMVC proxy the way the game registers it: by full type name, else by short name.</summary>
    public static T Proxy<T>(string name) where T : Il2CppObjectBase
    {
        var facade = GameFacade.Instance ?? throw new BridgeException("not_online", "the game has not finished starting");
        foreach (var key in new[] { $"GameRiver.Client.{name}", name })
        {
            var proxy = facade.RetrieveProxy(key)?.TryCast<T>();
            if (proxy is not null)
                return proxy;
        }
        throw new BridgeException("not_online", $"{name} is unavailable; wait for the main menu");
    }

    public static bool IsOnline()
    {
        try
        {
            return Proxy<ServerProxy>("ServerProxy").IsOnline();
        }
        catch (BridgeException)
        {
            return false;
        }
    }

    public static void RequireOnline()
    {
        if (!IsOnline())
            throw new BridgeException("not_online", "the game is not online; wait for it to log in");
    }

    public static string Version => UnityEngine.Application.version;

    public static string ReplayDirectory => FileUtility.ReplayDirectoryFullPath;
}
