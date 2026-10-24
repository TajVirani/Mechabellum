// Development only: feeds the store hand-made events in the shapes of docs/visualizer.md "SSE events", so the
// frontend renders without the backend. Query options:
//   ?setup        no localPlayerId (shows the setup card)
//   ?nomodel      modelAvailable false
//   ?spectate     localIndex null
//   ?status=<s>   status state (default live)
//   ?view=current open on the Current Match view after catch-up
import { start } from "../app.js";
import { applyEvent, ui } from "../store.js";
import { compositionOf } from "../roles.js";

const params = new URLSearchParams(location.search);
const ME = "281474976710769865";
const OPPONENTS = [
  ["281474976711365410", "Legion"],
  ["281474976710000101", "IronTide"],
  ["281474976710000102", "Kestrel"],
  ["281474976710000103", "nullptr"],
  ["281474976710000104", "Gravemind"],
  ["281474976710000105", "MossyRock"],
  ["281474976710000106", "Vantablack"],
];
const SPECIALISTS = [
  [20024, "Speed Specialist"],
  [10002, "Supply Specialist"],
  [20031, "Heavy Armor Specialist"],
  [20012, "Mobility Specialist"],
];
const OPENINGS = [
  [9901, "3 Void Eye + 2 Tarantula", "Void Eye"],
  [9871, "3 Marksman + 2 Sledgehammer", "Marksman"],
  [9873, "3 Crawler + 2 Mustang", "Crawler"],
  [9874, "3 Fang + 2 Steel Ball", "Fang"],
  [9880, "3 Arclight + 2 Sledgehammer", "Arclight"],
  [9881, "3 Arclight + 2 Fang", "Arclight"],
];
const UNIT_POOL = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 18, 19, 20, 22, 24, 26, 28, 30, 31, 32, 2002, 5015];

let seed = 7;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
const pick = (xs) => xs[Math.floor(rand() * xs.length)];

function composition(round) {
  const units = Array.from({ length: 2 + Math.floor(rand() * 5) }, () => ({ unitId: pick(UNIT_POOL), sellSupply: 100 * (1 + Math.floor(rand() * 4)) }));
  return compositionOf(units, round);
}

function summary(i) {
  const day = new Date(Date.UTC(2026, 8, 10) + Math.floor(i / 3) * 86400000);
  const ymd = day.toISOString().slice(0, 10);
  const battleId = `${ymd.replaceAll("-", "")}--${String(30000000 + (i % 3) * 3600000 + Math.floor(rand() * 1000000))}`;
  const won = rand() < 0.55;
  const [oppId, oppName] = pick(OPPONENTS);
  const [specId, specName] = pick(SPECIALISTS);
  const [openId, openName, lead] = pick(OPENINGS);
  const rounds = 4 + Math.floor(rand() * 7);
  const fights = Array.from({ length: rounds }, () => (rand() < 0.5 ? "Win" : "Lose"));
  const fielded = [...new Set(Array.from({ length: 3 + Math.floor(rand() * 5) }, () => pick(UNIT_POOL)))];
  const version = i < 25 ? ["2.0.0.4.2331", 2331] : ["2.0.0.5.2340", 2340];
  const mode = rand() < 0.85 ? "Normal" : "AsyncBattle";
  const comp = Array.from({ length: rounds }, (_, r) => composition(r + 1));
  return {
    battleId,
    date: ymd,
    replayPath: `C:/Replay/${version[0]}/${battleId}.grbr`,
    replayVersion: version[1],
    gameVersion: version[0],
    gameMode: mode,
    mapId: 1001,
    rounds,
    winnerIndex: won ? 0 : 1,
    players: [
      { playerId: ME, name: i < 30 ? "Sleep Deprived" : "SleepDeprived", won, specialistId: specId, specialistName: specName, openingId: openId, openingName: openName, openingLead: lead, fieldedUnitIds: fielded, fightResults: fights, finalHp: won ? 1200 + Math.floor(rand() * 3000) : 0, composition: comp },
      { playerId: oppId, name: oppName, won: !won, specialistId: 20024, specialistName: "Speed Specialist", openingId: 9873, openingName: "3 Crawler + 2 Mustang", openingLead: "Crawler", fieldedUnitIds: [10, 7, 1], fightResults: fights.map((f) => (f === "Win" ? "Lose" : "Win")), finalHp: won ? 0 : 900, composition: comp },
    ],
  };
}

function unit(unitId, unitName, level, sellSupply, x) {
  return { unitId, unitName, formationIndex: 0, rawLevel: level - 1, displayLevel: level, experience: 0, x, y: 40, isRotated: false, sellSupply, roundCount: 2, equipment: [] };
}

function player(id, name, rating, units, hp, supply, income) {
  return {
    playerId: id, name, team: 0, rating, state: "Deploying", supply, reactorCore: hp, maxReactorCore: 4500, roundSupplyIncome: income,
    previousFightResult: "Win", fightResultHistory: null, units, activeTechnologies: [], equipmentInventory: null, commanderSkills: null,
    officerIds: [20024], buildings: null, contraptions: null, blueprintIds: null, energyTowerSkillIds: null, towerStrengthenLevels: null,
    unlockedUnitIds: null, lockedUnitIds: null, lastFightReport: null, reactorCoreHistory: null, supplyHistory: null,
    reinforcementChoice: null, openingLineup: { advanceTeamId: 9901, offerIndex: 0 }, roundActions: null,
  };
}

const BATTLE = "20261024--67163824";
const BOARDS = {
  1: [[unit(30, "Void Eye", 1, 100, 10), unit(30, "Void Eye", 1, 100, 20), unit(30, "Void Eye", 1, 100, 30), unit(24, "Tarantula", 1, 200, 40), unit(24, "Tarantula", 1, 200, 50)],
      [unit(10, "Crawler", 1, 100, 10), unit(10, "Crawler", 1, 100, 20), unit(10, "Crawler", 1, 100, 30), unit(7, "Mustang", 1, 200, 40), unit(7, "Mustang", 1, 200, 50)]],
};
function boardsAt(round) {
  const [a, b] = BOARDS[1];
  const extraA = [unit(15, "Arclight", 2, 200, 60), unit(2002, "Mountain", 1, 800, 70), unit(26, "Farseer", 1, 300, 80), unit(9, "Fang", 1, 100, 90), unit(5015, "Unknown unit (5015)", 1, 150, 95)];
  const extraB = [unit(1, "Fortress", 1, 400, 60), unit(11, "Overlord", 1, 500, 70), unit(10, "Crawler", 1, 100, 80), unit(19, "Scorpion", 2, 450, 90), unit(13, "Sledgehammer", 2, 300, 100)];
  return [[...a, ...extraA.slice(0, round - 1)], [...b, ...extraB.slice(0, round - 1)]];
}

function frame(round, phase) {
  const [ua, ub] = boardsAt(round);
  const hpA = 4500 - (round - 1) * 380;
  const hpB = 4500 - (round - 1) * 520;
  const snapshot = {
    schemaVersion: 2,
    gameBuild: { replayVersion: 2340, gameVersion: "2.0.0.5", gameAssemblySha256: null },
    source: { type: "memory", uri: "memory://Mechabellum/1", capturedAtUtc: new Date().toISOString() },
    match: { battleId: BATTLE, mapId: 1031, gameMode: "Normal", matchMode: "VS_1_1", round, phase, reinforcementOffer: phase === "deploying" ? [10007, 20023, 13030001, 1306002] : [] },
    players: [player(ME, "Sleep Deprived", 2187, ua, hpA, 150 + round * 20, 200 + round * 50), player("281474976711365410", "Legion", 2235, ub, hpB, 90, 200 + round * 50)],
    outcome: null,
  };
  const localIndex = params.has("spectate") ? null : 0;
  return {
    snapshot,
    localIndex,
    composition: snapshot.players.map((p) => compositionOf(p.units, round)),
    boardAsOfLastFight: [false, localIndex != null && phase === "deploying"],
    offerNames: ["Quick Cooldown", "Elite Specialist", "Charged Shot", "Photon Coating"],
  };
}

function baseline() {
  const byRound = {};
  for (let r = 1; r <= 12; r++) {
    const c = composition(r);
    byRound[String(r)] = { roles: c.roles, air: c.air, hitsAir: c.hitsAir, bodies: c.bodies, n: r > 9 ? 3 : 40 - r * 3, thin: r > 9 };
  }
  const o = composition(0);
  return { byMode: { Normal: { byRound, overall: { roles: o.roles, air: o.air, hitsAir: o.hitsAir, bodies: o.bodies, n: 260, thin: false } } } };
}

function catchUp() {
  const rows = Array.from({ length: 64 }, (_, i) => summary(i));
  const ratings = {};
  rows.slice(-18).forEach((s, k) => {
    ratings[s.battleId] = { [ME]: 2100 + k * 6 + Math.floor(rand() * 30), [s.players[1].playerId]: 2050 + Math.floor(rand() * 300) };
  });
  applyEvent("hello", {
    serverVersion: "dev",
    localPlayerId: params.has("setup") ? null : ME,
    suggestedPlayerId: ME,
    modelAvailable: !params.has("nomodel"),
    replayDir: "C:/Replay",
    liveSource: "memory",
  });
  applyEvent("summaries", { rows });
  applyEvent("baseline", baseline());
  applyEvent("ratings", { byBattle: ratings });
  applyEvent("status", { state: params.get("status") || "live", detail: null, gameVersion: "2.0.0.5", bridge: "online", indexing: params.has("indexing") ? { done: 12, total: 66 } : { done: 64, total: 64 } });
  // Earlier rounds' fight ends, then the current deploying frame.
  for (let r = 1; r <= 5; r++) {
    applyEvent("frame", frame(r, "fight_over"));
  }
  applyEvent("frame", frame(6, "deploying"));
  const probs = [0.52, 0.47, 0.61, 0.58, 0.72];
  applyEvent("predictions", { battleId: BATTLE, rows: probs.map((p, i) => ({ round: i + 1, leftWinProbability: p, swing: i ? p - probs[i - 1] : 0 })) });
}

globalThis.process = { env: { NODE_ENV: "production" } };
await start({ live: false });
catchUp();
if (!params.has("view")) ui.view.set("stats");
else ui.view.set(params.get("view"));

// A couple of incremental events, to exercise the Recent highlight and the prediction upsert.
setTimeout(() => {
  const row = summary(64);
  row.battleId = "20261024--90000000";
  row.date = "2026-10-24";
  applyEvent("summary", { row });
  applyEvent("rating", { battleId: row.battleId, playerId: ME, rating: 2240 });
}, 1200);
