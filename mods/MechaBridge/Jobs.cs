using Il2CppGameRiver;
using Il2CppGameRiver.Client;
using Il2CppGoogle.Protobuf;
using Il2CppProtos.Match;
using MechaBridge.Protocol;
using CompetitionController = Il2CppGameRiver.Client.Competition.CompetitionController;

namespace MechaBridge;

/// <summary>
/// Request handlers. Each calls the same game functions the tournament history window uses,
/// so the game's servers see the same requests a player clicking through the window would send.
/// </summary>
internal static class Jobs
{
    private const int EndedState = 5;
    private const double ReplyTimeoutSeconds = 30;
    private const double DownloadTimeoutSeconds = 120;

    public static IEnumerator<Envelope?> Create(Scheduler scheduler, Envelope request) => request.BodyCase switch
    {
        Envelope.BodyOneofCase.StatusRequest => Status(scheduler),
        Envelope.BodyOneofCase.ListCompetitionsRequest => ListCompetitions(scheduler, request.ListCompetitionsRequest.Page),
        Envelope.BodyOneofCase.CompetitionPageRequest => CompetitionPage(scheduler, request.CompetitionPageRequest),
        Envelope.BodyOneofCase.DownloadReplayRequest => DownloadReplay(scheduler, request.DownloadReplayRequest.ReplayPath),
        _ => Fail("invalid_request", $"unsupported request {request.BodyCase}"),
    };

    private static IEnumerator<Envelope?> Fail(string code, string message)
    {
        yield return Replies.Error(0, code, message);
    }

    private static IEnumerator<Envelope?> Status(Scheduler scheduler)
    {
        yield return new Envelope
        {
            StatusReply = new StatusReply
            {
                ProtocolVersion = 1,
                ModVersion = "0.1.0",
                GameVersion = Game.Version,
                Online = Game.IsOnline(),
                ReplayDirectory = Game.ReplayDirectory,
                ServerRequestIntervalMs = (uint)scheduler.ServerRequestIntervalMs,
            },
        };
    }

    private static IEnumerator<Envelope?> ListCompetitions(Scheduler scheduler, int page)
    {
        if (page < 1)
            throw new BridgeException("invalid_request", "page must be at least 1");
        Game.RequireOnline();
        var proxy = Game.Proxy<CompetitionProxy>("CompetitionProxy");

        foreach (var wait in scheduler.WaitForServerSlot())
            yield return wait;
        // The history window only sends an empty request (answered with page 1), and CompetitionProxy's
        // RequestHistoryMatch() is dropped while an identical request is in its resend cooldown. So the mod
        // builds the request with the page set, for every page, and sends it through the game's MessageCenterV2.
        ResponseHooks.ExpectHistory(page);
        if (MessageCenterV2.Instance.SendMsg(new RequestHistoryMatch { Page = page }.Cast<IMessage>(), null, 1f) == 0)
            throw new BridgeException("game_error", $"the game refused to send the request for page {page}");
        foreach (var wait in Scheduler.WaitUntil(() => ResponseHooks.History is not null, ReplyTimeoutSeconds, "the tournament list"))
            yield return wait;
        var reply = ResponseHooks.History!;

        if (page == 1)
        {
            // Ended mini tournaments are only in the recent list, which the game refreshes with RequestMatchList.
            foreach (var wait in scheduler.WaitForServerSlot())
                yield return wait;
            var generation = ResponseHooks.MatchListGeneration;
            if (proxy.RequestMatchList(1, 1f) != 0)
            {
                foreach (var wait in Scheduler.WaitUntil(
                             () => ResponseHooks.MatchListGeneration != generation, ReplyTimeoutSeconds, "the recent tournament list"))
                    yield return wait;
            }
            AddEndedRecent(reply);
        }
        yield return new Envelope { ListCompetitionsReply = reply };
    }

    private static void AddEndedRecent(ListCompetitionsReply reply)
    {
        var known = reply.Competitions.Select(competition => competition.Id).ToHashSet();
        var infos = CompetitionController.Instance.C_SystemData.C_MatchListData.MatchBaseInfos;
        for (var at = 0; at < infos.Count; at++)
        {
            var info = infos[at];
            if (info.State != EndedState || !known.Add(info.ID))
                continue;
            var competition = new Competition { Id = info.ID, StartTime = info.StartTime, Source = CompetitionSource.Recent };
            for (var sub = 0; sub < info.SubMatchs.Count; sub++)
                competition.SubIds.Add(info.SubMatchs[sub].Subid);
            reply.Competitions.Add(competition);
        }
    }

    private static IEnumerator<Envelope?> CompetitionPage(Scheduler scheduler, CompetitionPageRequest request)
    {
        if (request.CompetitionId <= 0 || request.SubId < 0 || request.Page < 1)
            throw new BridgeException("invalid_request", "competition_id and page must be positive and sub_id nonnegative");
        Game.RequireOnline();
        var proxy = Game.Proxy<CompetitionProxy>("CompetitionProxy");

        foreach (var wait in scheduler.WaitForServerSlot())
            yield return wait;
        ResponseHooks.ExpectDetail(request.CompetitionId, request.SubId, request.Page);
        proxy.RequestHistoryMatchDetail(request.CompetitionId, request.SubId, request.Page);
        foreach (var wait in Scheduler.WaitUntil(() => ResponseHooks.Detail is not null, ReplyTimeoutSeconds, "the tournament page"))
            yield return wait;
        yield return new Envelope { CompetitionPageReply = ResponseHooks.Detail! };
    }

    private static IEnumerator<Envelope?> DownloadReplay(Scheduler scheduler, string replayPath)
    {
        var target = SavedReplayPath(replayPath);
        var reply = new DownloadReplayReply { ReplayPath = replayPath, FilePath = target };
        if (File.Exists(target))
        {
            yield return new Envelope { DownloadReplayReply = reply };
            yield break;
        }
        Game.RequireOnline();
        var proxy = Game.Proxy<ReplayProxy>("ReplayProxy");

        // The proxy must have loaded the local replay index before it accepts downloads.
        foreach (var wait in Scheduler.WaitUntil(() => proxy.TryLoadReplay(false), ReplyTimeoutSeconds, "loading the replay list"))
            yield return wait;
        foreach (var wait in scheduler.WaitForServerSlot())
            yield return wait;
        proxy.DowloadServerReplay(replayPath);

        var started = DateTime.UtcNow;
        foreach (var wait in Scheduler.WaitUntil(
                     () => File.Exists(target) || TrySave(proxy, replayPath, target) || Failed(proxy, replayPath, started),
                     DownloadTimeoutSeconds,
                     $"downloading {replayPath}"))
            yield return wait;
        if (!File.Exists(target))
            throw new BridgeException("game_error", $"the game could not download {replayPath}");
        reply.Downloaded = true;
        yield return new Envelope { DownloadReplayReply = reply };
    }

    /// <summary>
    /// The history window saves the converted replay itself; when the download was started from here,
    /// save it the same way, through the game's FileUtility, to the same path.
    /// </summary>
    private static bool TrySave(ReplayProxy proxy, string replayPath, string target)
    {
        if (!proxy.TryGetReplayByPath(replayPath, out var found) || found?.TryCast<Replay>() is not { } replay)
            return false;
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        replay.GenerateBattleRecordData();
        FileUtility.SaveBinary(target, replay);
        return File.Exists(target);
    }

    private static bool Failed(ReplayProxy proxy, string replayPath, DateTime started) =>
        DateTime.UtcNow - started > TimeSpan.FromSeconds(2) && !proxy.CheckIsDownloadingByServer(replayPath);

    /// <summary>"2.0.0.4.2331/7698177661977234324.rep" is saved as Replay\2.0.0.4.2331\7698177661977234324.rep.grbr.</summary>
    private static string SavedReplayPath(string replayPath)
    {
        var parts = replayPath.Split('/');
        if (parts.Length != 2
            || parts[0].Length == 0
            || !parts[0].All(c => IsDigit(c) || c == '.')
            || !parts[1].EndsWith(".rep", StringComparison.Ordinal)
            || parts[1].Length == 4
            || !parts[1][..^4].All(IsDigit))
            throw new BridgeException("invalid_request", "replay_path must look like <version>/<numeric id>.rep");
        return Path.Combine(Game.ReplayDirectory, parts[0], parts[1] + ".grbr");
    }

    private static bool IsDigit(char c) => c is >= '0' and <= '9';
}
