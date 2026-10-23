# What Mechabellum players want from stats and match-tracking tools

Research for wayfinder ticket `.scratch/visualizer/issues/01-research-what-players-want.md`.
Surveyed 2026-10-23. Terms (Visualizer, Stats view, Current Match view, Local Player) follow `GLOSSARY.md`.

## Summary

- **Few Mechabellum tools exist, and none of them is a personal stats site.** I found no third-party match-history, win-rate or pick-rate site for Mechabellum. Players have asked for one since 2023 and still track results by hand in spreadsheets ([S1], [S2], [S3], [S4]).
- **The two existing stats mods are about combat, not history.** GODOG's "Battle Suit Standard Match" HUD shows damage charts and spent supply for spectated games ([M1]). Mecha Community Mod (gue88who) shows live army combat stats, per-unit stats and a saved post-game report with round history and damage breakdowns ([M2]). Community counter calculators are the other common kind of tool ([T1], [T2]).
- **Players ask most for a personal W/L record and win rate.** They want it private, broken down by mode and by the specialist they picked, and with losses shown. Opponent stats come next, though some players push back on those. After that come post-match unit performance (damage, kills, most valuable unit), with requests repeated across 2023 and 2024.
- **Comparable auto-battler tools all converge on the same panels.** Firestone and HSReplay for Hearthstone Battlegrounds, and MetaTFT for TFT ([C1]–[C5]):
  - Stats side: a rating graph over time, per-hero or per-comp tables (games, placement or win rate, rating delta), a session recap, and round-by-round history of each game.
  - Live side: battle or win odds, an HP graph for all players, and the opponent's last known board.
- **The Current Match view's centrepiece has good precedent.** Riot's broadcast win-probability graph plots time on x and WP on y with a 50% midline, and marks events with the size of their swing. Riot shows it after key plays and warns that WP describes the current state, not a forecast ([C6]).
- **Biggest data gap.** MatchSnapshot v2 has no combat telemetry: no per-unit damage, kills or damage taken. Replays store inputs and seeds, not combat results ([G1], [G2]). The most-requested post-match stat, damage dealt per unit, is therefore **not supportable** without a combat simulator or a new memory read. Everything built on outcome, rounds, HP, supply, units, techs, cards and opponent identity is supportable.
- **Reddit could not be surveyed.** reddit.com is blocked to this research agent's fetcher and search. The Reddit evidence is missing, not negative. A human pass over r/Mechabellum, searching "stats", "tracker" and "win rate", is a cheap follow-up.

## Ranked candidates: Stats view (Local Player's personal history)

Ranking weighs (a) how often Mechabellum players ask for it, (b) whether comparable tools converge on it, and (c) how feasible it is from v2. The "Freq" column counts independent Mechabellum sources and comparable tools.

| # | Panel | Evidence / frequency | v2 support |
|---|---|---|---|
| 1 | **Overall record: W/L, win rate, games played** (private, losses included) | Most-requested item. 4 Steam threads, 2023–2024 ([S1], [S2], [S3], [S4]), plus a spreadsheet workaround in [S1]. Every comparable tool has it ([C1], [C3], [C4]). | **Yes.** `outcome.winnerName` / `winnerPlayerId` against the Local Player's `players[].name`. |
| 2 | **Win rate by mode** (and by map) | Asked for explicitly: "wins/losses … on what mode" [S3]. Map and mode filters are standard elsewhere ([C4]). | **Yes.** `match.gameMode`, `match.matchMode`, `match.mapId` (map names need an id table). |
| 3 | **Win rate by specialist / opening choice** | "…with whatever leader I chose" [S3]. Per-hero tables (games, placement, rating delta) are the core of Firestone and HSReplay ([C1], [C2]). | **Yes, with id tables.** `officerIds`, `commanderSkills`, `openingLineup.advanceTeamId`. Names wait on the round 2 id tables. |
| 4 | **Unit pick frequency and win rate when fielded** | Asked for repeatedly ("which units have higher win rates") [S5], and recurs in [S2]. Most-used comps and units appear in TFT profiles ([C4]). Note: [S5] wanted global meta data; the Visualizer can only give the personal version. | **Yes.** `units[].unitId` / `unitName` per round, plus `outcome`. Pick timing comes from `roundActions` (`PAD_BuyUnit`). |
| 5 | **Rating over time** | Firestone's MMR graph and HSReplay's MMR-over-time ([C1], [C2]). For Mechabellum, players complain the MMR display is unreliable [S3]. | **Partial.** `rating` is live-only; replays leave it `null` (contracts/README). Points exist only for matches the live recorder saw. |
| 6 | **Recent matches list → per-match round timeline** (HP both sides, result per round, units bought) | Asked for as a "round history" ([S6], [S7]). Mecha Community Mod's report includes round history [M2]. MetaTFT sells round-by-round history [C3]. Players currently scroll the in-game battle log [S2]. | **Yes.** `reactorCore` and `fightResultHistory` per `fight_over` snapshot, plus `roundActions`. The last fight has no snapshot (contracts/README, Snapshot timing), so the final round must be inferred from `outcome`. |
| 7 | **Economy habits** (supply spent per round, unspent supply, reinforcement card picks) | "Money spent, money earned" [S6]. GODOG's HUD shows "spent supplies" [M1]. MetaTFT compares leveling and economy habits [C3]. | **Mostly.** `supply` and `roundActions` are available. Costs need the round 2 cost tables. `roundSupplyIncome` is live-only. `reinforcementOffer` / `reinforcementChoice` are available. |
| 8 | **Record vs. opponents (head-to-head, opponent rating at match time)** | Asked for in [S2] and [S3], opposed in [S2] and [S1]. Firestone shows opponent MMR [C1]. Contested, so keep it personal (your record against X), never a public profile. | **Yes** for name and result (`players[].name`). Opponent `rating` is live-only. |
| 9 | **Session recap** (games today, W/L, rating change since session start) | Firestone's session recap widget [C1]. No direct Mechabellum request. | **Yes.** Uses `source.capturedAtUtc` (or replay file time) with `outcome`. Rating delta is live-only. |
| 10 | **Tech and equipment choices with win rate** | Tech opinions are popular in guides (MechaMonarch, [T3]). Weak direct demand for personal stats. | **Yes, with id tables.** `activeTechnologies`, `units[].equipment`, `equipmentInventory`. |
| — | *Per-unit damage / kills / MVP across matches* | Second most requested overall ([S2], [S6], [S7], [S8]). | **No.** Not in v2 or replays ([G1], [G2]). Reading it would need Mecha Community Mod-style memory reads of combat stats or a simulator. Park it after v1. |

## Ranked candidates: Current Match view (live, centred on win probability)

| # | Panel | Evidence / frequency | v2 support |
|---|---|---|---|
| 1 | **Win-probability timeline** (per round, 50% midline, swing size marked per round) | The ticket's centre. Riot's WP graph is the canonical design, with swing markers on events [C6]. Battle-odds overlays are the most-used live feature in comparable tools: Bob's Buddy [C5], Firestone [C1], MetaTFT "win chance" [C3]. | **Yes.** `live-predict` runs on the first `FightOver` frame per round. History is missing if the reader joined mid-match (`fightResultHistory` is `null`). |
| 2 | **HP (reactor core) per round, both players** | Firestone's live HP graph [C1]. HP is the win condition: 4,500 base, damage from surviving units [W1]. "Rounds won" is asked for in [S6]. | **Yes.** `reactorCore`, `maxReactorCore` (live), `fightResultHistory`. |
| 3 | **Army value and supply comparison** (army value on board, unspent supply, income) | GODOG's HUD shows "spent supplies" [M1]. Mecha Community Mod shows live army stats [M2]. "Money spent / earned" [S6]. | **Yes.** `units[].sellSupply`, `supply`, `roundSupplyIncome` (live). Cost tables improve accuracy. |
| 4 | **Board summary: both armies' units, levels, techs, equipment** (the opponent's last-known board) | Firestone's "opponent's last board" and warband panel [C1]. Spectators want card selections visible [S9]. Counter calculators take exactly this as input ([T1], [T2]). | **Yes.** `units`, `activeTechnologies`, `equipment`, `reinforcementChoice`. Names and icons need id tables. |
| 5 | **"Why did WP move" driver breakdown** (top features behind this round's change) | Riot explains WP movement through its model inputs and says viewers need education to read it [C6]. No Mechabellum demand found. | **Yes, if the model exposes contributions.** Depends on the `live-predict` model, not the data. |
| 6 | **Card offer and pick this round** | Spectators want card selections visible in 2v2 [S9]. Card stats are core to HSReplay and MetaTFT (augments) ([C2], [C3]). | **Yes.** `match.reinforcementOffer` and `reinforcementChoice`, both live. |
| 7 | **Counter hints vs. opponent army** | Two community counter tools exist ([T1], [T2]), and counter-picking dominates the Q&A threads [S5]. | **Plausible, outside the data.** Needs a static counter table. Grey area under the mod rule? It only reads data the server sends, but treat it as advice and check it against [M1]'s "grey area" note. Out of v1. |
| 8 | **Ratings of both players** | Firestone shows opponent MMR [C1]. Players ask to see the opponent's MMR [S3]. | **Yes.** `rating` (live, 1v1 Elo). |
| — | *Live per-unit damage meter* | GODOG's and gue88who's mods both do this ([M1], [M2]), and it is the most-built Mechabellum mod feature. | **No.** No combat telemetry in v2. Would need new memory reads. Defer. |

## Mod-rule check

The Mechabellum team's working statement, relayed on the wiki Mod page [M1], is this: client-side QoL mods that show stats (damage statistics, drop sale values) are tolerated at the player's own risk. Mods that go further are a "grey area" (the examples are Sentry Missile target arrows and Mobile Beacon target highlighting). Mods that send data to the server are bannable. Every panel above only displays data the client already holds, so none conflicts with the rule. Counter hints (#7 live) sit closest to the "grey area", because they advise the player during a match.

## Sources

Mechabellum mods and tools
- [M1] mechabellum.wiki.gg, *Mod*: https://mechabellum.wiki.gg/wiki/Mod. Lists the GODOG Battle Suit Standard Match HUD (damage charts, spent supplies), the llxlzx Mod Manager and Auto Speed Up, and gives the developer policy.
- [M2] gue88who/MechaCommunityMod: https://github.com/gue88who/MechaCommunityMod. F8 live army stats, per-unit stats, post-game report with round history and damage breakdowns; targets 2.0.0.3.2328. Has 0 stars, so its reach is unknown.
- [M3] llxlzx/MechabellumModManager: https://github.com/llxlzx/MechabellumModManager. Mod hub and catalog. Its listing names no stats mods beyond `BlackBox`.
- [T1] Mechabellum Companion counter calculator: https://mechabellum-companion.netlify.app/
- [T2] MechCounter: https://mechacounter.com/
- [T3] MechaMonarch unit tier list: https://mechamonarch.com/guide/mechabellum-unit-tier-list/
- [G1] IcyIcyD/MechabellumReplayParser README: https://github.com/IcyIcyD/MechabellumReplayParser. Says replays are an input log, with no combat results.
- [G2] Steam: "Replay files analysis … completely deterministic": https://steamcommunity.com/app/669330/discussions/0/6980058383081206081/
- [W1] mechabellum.wiki.gg, *Player Hit Points*: https://mechabellum.wiki.gg/wiki/Player_Hit_Points

Mechabellum community requests (Steam)
- [S1] "Can we see our W/L record?" (May 2023, 5 replies; a spreadsheet workaround): https://steamcommunity.com/app/669330/discussions/0/3825289852112192875/
- [S2] "More statistics (wish to the developers)" (Oct–Nov 2024; asks for own W/L and win rate, opponent stats, and a post-game MVP/kills screen; opponent stats contested): https://steamcommunity.com/app/669330/discussions/0/4694532371788184610/
- [S3] "MMR Search & Statistics" (Jun 2024; asks for opponent MMR, own stats, and W/L by mode and leader): https://steamcommunity.com/app/669330/discussions/1/4336483106369697536/
- [S4] Steam thread asking for win/loss and unit win rates (Nov 2024): https://steamcommunity.com/app/669330/discussions/0/7004881118891648277
- [S5] Same thread as [S4]: unit win-rate rankings, plus counter-pick replies.
- [S6] "QoL, Feedback & Bugs" (May–Jul 2023; match recap with damage, units destroyed, money spent and earned, rounds won, and per-round unit stats): https://steamcommunity.com/app/669330/discussions/0/3825289852121238468/
- [S7] "We need STATISTICS after the match!" (Dec 2024; asks which unit did the most damage, and for unit info in a table): https://steamcommunity.com/app/669330/discussions/0/598512477964164041/
- [S8] "Can we have the attack values also show the number of shots fired?": https://steamcommunity.com/app/669330/discussions/0/600780667249278169/
- [S9] "Spectating and replay need more options" (Jul 2024; 2v2 card selections, rewind and round skip): https://steamcommunity.com/app/669330/discussions/1/6874265367086538126/

Comparable auto-battler tools
- [C1] Firestone features wiki (Battlegrounds): https://github-wiki-see.page/m/Zero-to-Heroes/firestone/wiki/Firestone-features. Covers the MMR graph, per-hero stats, session recap, battle odds, live HP graph for all players, opponent last board, and battle history.
- [C2] HSReplay Battlegrounds Tier7: https://hsreplay.net/battlegrounds/tier7. Returned 403 to the fetcher. Features (MMR over time, per-hero games, net MMR, placement distribution) are taken from the search snippet.
- [C3] MetaTFT on Overwolf: https://www.overwolf.com/app/MetaTFT.com-MetaTFT. Marketing copy: win chance, round-by-round match history, economy habits, lobby scouting.
- [C4] Mobalytics TFT profile guide: https://mobalytics.gg/blog/tft/tft-how-to-use-mobalytics-profile/. Returned 403. Features (placement distribution, filters by champion or synergy, top comps) are taken from the search snippet.
- [C5] HSReplay Bob's Buddy FAQ: https://hsreplay.net/battlegrounds/overlay/. Runs 10,000+ combat simulations at combat start to give win, tie and loss odds.
- [C6] Riot dev diary, *Win Probability powered by AWS*: https://lolesports.com/en-US/news/dev-diary-win-probability-powered-by-aws-at-worlds. Describes the WP graph design, event swing markers and presentation caveats.

Not reached
- reddit.com (r/Mechabellum): blocked to both fetch and search for this agent.
- Discord servers (official, GODOG Battalion): not publicly indexable.
- Searches for a Mechabellum Twitch extension or OBS overlay returned nothing Mechabellum-specific.
