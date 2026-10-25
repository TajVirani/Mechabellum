using HarmonyLib;
using Il2CppGameRiver.Client;
using Il2CppInterop.Runtime.InteropTypes;
using Il2CppProtos.Match;
using EFightReason = Il2CppProtos.Fight.EFightReason;
using FightRecord = Il2CppProtos.Common.FightRecord;
using PlayerMinimalInfo = Il2CppProtos.Common.PlayerMinimalInfo;
using ResponseFPDetail = Il2CppProtos.FpRecord.ResponseFPDetail;
using MechaBridge.Protocol;

namespace MechaBridge;

/// <summary>
/// Observes the game's own handling of tournament and match history replies. The prefixes copy what the bridge needs
/// into managed objects before the game's handler runs, and never change the arguments or skip the handler.
/// The one exception is the history window's list refresh, skipped for replies the mod asked for (see <see cref="WindowRefreshHook"/>).
/// </summary>
internal static class ResponseHooks
{
    private static readonly object Gate = new();
    private static ListCompetitionsReply? _history;
    private static int _historyPage;
    private static CompetitionPageReply? _detail;
    private static (int Id, int SubId, int Page) _detailKey;
    private static bool _handlingOwnDetail;
    private static PersonalHistoryReply? _personalHistory;
    private static bool _expectPersonalHistory;

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

    public static void ExpectPersonalHistory()
    {
        lock (Gate)
        {
            _personalHistory = null;
            _expectPersonalHistory = true;
        }
    }

    public static PersonalHistoryReply? PersonalHistory
    {
        get { lock (Gate) return _personalHistory; }
    }

    /// <summary>
    /// The match history reply only fills the proxy's record list, which the power record tab reads when it is shown.
    /// No window refreshes on it, so unlike the tournament detail it needs no guard.
    /// </summary>
    [HarmonyPatch(typeof(PowerRecordProxy), nameof(PowerRecordProxy.OnResponseFPDetail))]
    private static class PersonalHistoryHook
    {
        private static void Prefix(ResponseFPDetail __1)
        {
            var message = __1;
            if (message is null)
                return;
            lock (Gate)
            {
                if (!_expectPersonalHistory)
                    return;
            }
            var reply = new PersonalHistoryReply();
            var records = message.Records;
            for (var at = 0; at < records.Count; at++)
            {
                if (records[at] is { } record)
                    reply.Matches.Add(ToPersonalMatch(record));
            }
            lock (Gate)
            {
                _personalHistory = reply;
                _expectPersonalHistory = false;
            }
        }
    }

    private static PersonalMatch ToPersonalMatch(FightRecord record)
    {
        var match = new PersonalMatch
        {
            Time = record.Time,
            MapId = record.MapId,
            Reason = record.Reason,
            ReasonName = ((EFightReason)record.Reason).ToString(),
            Point = record.Point,
            EloPoint = record.EloPoint,
            IsPlacementMatch = record.IsPlacementMatch,
            Season = record.Season,
            IsFun = record.IsFun,
        };
        switch (record.ExtendCase)
        {
            case FightRecord.ExtendOneofCase.Lobby when record.Lobby is { } lobby:
                match.Kind = PersonalMatchKind.Lobby;
                match.Win = lobby.Win;
                match.Index = lobby.Index;
                AddPlayers(match, lobby.Players);
                break;
            case FightRecord.ExtendOneofCase.Match when record.Match is { } competition:
                match.Kind = PersonalMatchKind.Competition;
                match.Win = competition.Win;
                match.Index = competition.Index;
                match.CompetitionId = competition.Id;
                match.CompetitionRound = competition.Round;
                AddPlayers(match, competition.Players);
                break;
            case FightRecord.ExtendOneofCase.ChaosFaction when record.ChaosFaction is { } chaos:
                match.Kind = PersonalMatchKind.ChaosFaction;
                match.Rank = chaos.Rank;
                match.Index = chaos.Index;
                AddPlayers(match, chaos.Players);
                break;
            case FightRecord.ExtendOneofCase.Level:
                match.Kind = PersonalMatchKind.Level;
                break;
            case FightRecord.ExtendOneofCase.Course:
                match.Kind = PersonalMatchKind.Course;
                break;
        }
        var mine = match.Players.Where(player => player.Index == match.Index).ToList();
        if (mine.Count == 1)
            match.MyUserId = mine[0].UserId;
        // Read as a player index, `win` names the winner; read as a flag, it says whether the record's own player won.
        // With two players the readings name the same winner exactly when the record's own index is not 0.
        if (match.Kind is PersonalMatchKind.Lobby or PersonalMatchKind.Competition
            && match.Players.Count == 2
            && mine.Count == 1
            && match.Index != 0)
        {
            var other = match.Players.First(player => player.Index != match.Index);
            var byIndex = match.Players.Where(player => player.Index == match.Win).ToList();
            var byFlag = match.Win != 0 ? mine[0] : other;
            if (byIndex.Count == 1 && byIndex[0].UserId == byFlag.UserId)
                match.WinnerUserId = byFlag.UserId;
        }
        return match;
    }

    private static void AddPlayers(PersonalMatch match, Il2CppGoogle.Protobuf.Collections.RepeatedField<PlayerMinimalInfo>? players)
    {
        if (players is null)
            return;
        for (var at = 0; at < players.Count; at++)
        {
            if (players[at] is { } player)
                match.Players.Add(new PersonalMatchPlayer { UserId = player.Userid, Index = player.Index, Name = player.Name ?? "" });
        }
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
            _handlingOwnDetail = false;
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
            // Each replay is listed once per team, under that team's slot, with that team's Win.
            var results = new Dictionary<string, ReplayResult>();
            for (var rank = 0; rank < message.RankList.Count; rank++)
            {
                var slot = message.RankList[rank];
                var members = slot.TeamInfo?.Members;
                var userId = members is not null && members.Count > 0 ? members[0].Userid : 0UL;
                var records = slot.RoundRecord;
                for (var at = 0; at < records.Count; at++)
                {
                    var record = records[at];
                    var path = record.ReplayPath;
                    if (string.IsNullOrEmpty(path))
                        continue;
                    if (!results.TryGetValue(path, out var result))
                    {
                        result = new ReplayResult { ReplayPath = path };
                        results.Add(path, result);
                        reply.ReplayPaths.Add(path);
                        reply.Results.Add(result);
                    }
                    if (record.Win)
                        result.WinnerUserId = userId;
                    else
                        result.LoserUserId = userId;
                }
            }
            lock (Gate)
            {
                if ((reply.CompetitionId, reply.SubId, reply.Page) == _detailKey)
                {
                    // Still waiting means the mod sent the request; a player opening the same page meanwhile is not told apart.
                    _handlingOwnDetail = _detail is null;
                    _detail = reply;
                }
            }
        }

        private static void Postfix() => _handlingOwnDetail = false;
    }

    /// <summary>
    /// The game's detail handler notifies the history window's mediator, whose RefreshList throws a
    /// NullReferenceException when the window was never opened. For the mod's own requests the refresh is
    /// skipped; replies to the window's requests refresh it as usual.
    /// </summary>
    [HarmonyPatch(typeof(Competition_HistoryWindow), nameof(Competition_HistoryWindow.RefreshList))]
    private static class WindowRefreshHook
    {
        private static bool Prefix() => !_handlingOwnDetail;
    }

    [HarmonyPatch(typeof(CompetitionProxy), nameof(CompetitionProxy.OnResponseMatchList))]
    private static class MatchListHook
    {
        private static void Postfix() => MatchListGeneration++;
    }
}
