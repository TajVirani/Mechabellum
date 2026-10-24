using HarmonyLib;
using Il2CppGameRiver.Client;
using Il2CppInterop.Runtime.InteropTypes;
using Il2CppProtos.Match;
using MechaBridge.Protocol;

namespace MechaBridge;

/// <summary>
/// Observes the game's own handling of tournament replies. The prefixes copy what the bridge needs
/// into managed objects before the game's handler runs, and never change the arguments or skip the handler.
/// </summary>
internal static class ResponseHooks
{
    private static readonly object Gate = new();
    private static ListCompetitionsReply? _history;
    private static int _historyPage;
    private static CompetitionPageReply? _detail;
    private static (int Id, int SubId, int Page) _detailKey;

    public static int MatchListGeneration { get; private set; }

    public static void ExpectHistory(int page)
    {
        lock (Gate)
        {
            _history = null;
            _historyPage = page;
        }
    }

    public static ListCompetitionsReply? History
    {
        get { lock (Gate) return _history; }
    }

    public static void ExpectDetail(int id, int subId, int page)
    {
        lock (Gate)
        {
            _detail = null;
            _detailKey = (id, subId, page);
        }
    }

    public static CompetitionPageReply? Detail
    {
        get { lock (Gate) return _detail; }
    }

    [HarmonyPatch(typeof(CompetitionProxy), nameof(CompetitionProxy.OnResponseHistoryMatch))]
    private static class HistoryHook
    {
        private static void Prefix(ResponseHistoryMatch __1)
        {
            var message = __1;
            if (message is null)
                return;
            // Pages start at 1; the reply to the window's empty request leaves the page unset (0).
            var page = Math.Max(message.Page, 1);
            var reply = new ListCompetitionsReply { Page = page, PageCount = message.PageNum };
            for (var at = 0; at < message.Datas.Count; at++)
            {
                var data = message.Datas[at];
                var competition = new Competition { Id = data.Id, StartTime = data.StartTime, Source = CompetitionSource.History };
                for (var sub = 0; sub < data.SubidArr.Count; sub++)
                    competition.SubIds.Add(data.SubidArr[sub]);
                reply.Competitions.Add(competition);
            }
            lock (Gate)
            {
                if (page == _historyPage)
                    _history = reply;
            }
        }
    }

    [HarmonyPatch(typeof(CompetitionProxy), nameof(CompetitionProxy.OnResponseHistoryMatchDetail))]
    private static class DetailHook
    {
        private static void Prefix(ResponseHistoryMatchDetail __1)
        {
            var message = __1;
            if (message is null)
                return;
            var reply = new CompetitionPageReply
            {
                CompetitionId = message.Id,
                SubId = message.SubInfo.Subid,
                State = message.SubInfo.State,
                Page = message.Page,
                PageCount = message.PageNum,
            };
            var seen = new HashSet<string>();
            for (var rank = 0; rank < message.RankList.Count; rank++)
            {
                var records = message.RankList[rank].RoundRecord;
                for (var at = 0; at < records.Count; at++)
                {
                    var path = records[at].ReplayPath;
                    if (!string.IsNullOrEmpty(path) && seen.Add(path))
                        reply.ReplayPaths.Add(path);
                }
            }
            lock (Gate)
            {
                if ((reply.CompetitionId, reply.SubId, reply.Page) == _detailKey)
                    _detail = reply;
            }
        }
    }

    [HarmonyPatch(typeof(CompetitionProxy), nameof(CompetitionProxy.OnResponseMatchList))]
    private static class MatchListHook
    {
        private static void Postfix() => MatchListGeneration++;
    }
}
