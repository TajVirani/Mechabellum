// Unit names and roles for the browser. Mirrors `unit_roles.json` (from research/unit-roles.md) and
// `collector/unit_catalog.py` UNIT_NAMES; the server owns the composition maths, this table only names units
// and colours their chips. A unit missing here is "unknown".

export const ROLES = ["chaff", "chaffClear", "damage", "tank", "support", "unknown"];

export const ROLE_LABELS = {
  chaff: "Chaff",
  chaffClear: "Chaff clear",
  damage: "Damage",
  tank: "Tank",
  support: "Support",
  unknown: "Unknown",
};

// id: [name, primary, secondary, air, hitsAir, members]
const TABLE = {
  1: ["Fortress", "tank", "damage", false, false, 1],
  2: ["Marksman", "damage", null, false, true, 1],
  3: ["Vulcan", "chaffClear", "tank", false, false, 1],
  4: ["Melting Point", "damage", null, false, true, 1],
  5: ["Rhino", "damage", "tank", false, false, 1],
  6: ["Wasp", "chaff", "damage", true, true, 12],
  7: ["Mustang", "damage", "chaff", false, true, 12],
  8: ["Steel Ball", "damage", "chaff", false, false, 4],
  9: ["Fang", "chaff", "damage", false, true, 18],
  10: ["Crawler", "chaff", null, false, false, 24],
  11: ["Overlord", "damage", "chaffClear", true, true, 1],
  12: ["Stormcaller", "chaffClear", "damage", false, false, 4],
  13: ["Sledgehammer", "tank", "chaff", false, false, 5],
  14: ["Hacker", "support", null, false, false, 1],
  15: ["Arclight", "chaffClear", null, false, false, 1],
  16: ["Phoenix", "damage", null, true, true, 2],
  17: ["War Factory", "tank", "damage", false, false, 1],
  18: ["Wraith", "chaffClear", "tank", true, true, 1],
  19: ["Scorpion", "damage", "tank", false, false, 1],
  20: ["Fire Badger", "chaffClear", null, false, false, 3],
  21: ["Sabertooth", "tank", "damage", false, false, 1],
  22: ["Typhoon", "chaffClear", "support", false, true, 2],
  23: ["Sandworm", "damage", "tank", false, false, 1],
  24: ["Tarantula", "chaffClear", "tank", false, false, 1],
  25: ["Phantom Ray", "damage", "chaffClear", true, true, 3],
  26: ["Farseer", "support", "damage", false, true, 1],
  27: ["Raiden", "chaffClear", "damage", true, true, 1],
  28: ["Hound", "chaffClear", "chaff", false, false, 5],
  29: ["Abyss", "damage", null, true, true, 1],
  30: ["Void Eye", "damage", null, false, false, 3],
  31: ["Vortex", "tank", "damage", false, false, 1],
  32: ["Centurion", "damage", "tank", false, true, 1],
  2002: ["Mountain", "tank", "damage", false, false, 1],
};

export function unitInfo(id) {
  const row = TABLE[id];
  if (!row) {
    return { id, name: `Unknown unit (${id})`, primary: "unknown", secondary: null, air: false, hitsAir: false, members: 1 };
  }
  const [name, primary, secondary, air, hitsAir, members] = row;
  return { id, name, primary, secondary, air, hitsAir, members };
}

export function unitName(id, fallback) {
  return TABLE[id] ? TABLE[id][0] : fallback || `Unknown unit (${id})`;
}

// Fallback only: the server sends `composition` with every frame. Used when a frame arrives without it.
export function compositionOf(units, round) {
  const roles = Object.fromEntries(ROLES.map((r) => [r, 0]));
  let supply = 0;
  let air = 0;
  let hitsAir = 0;
  let bodies = 0;
  for (const unit of units || []) {
    const info = unitInfo(unit.unitId);
    const value = Math.max(0, unit.sellSupply || 0);
    supply += value;
    roles[info.primary] += value;
    if (info.air) air += value;
    if (info.hitsAir) hitsAir += value;
    bodies += info.members;
  }
  if (supply > 0) {
    for (const r of ROLES) roles[r] /= supply;
    air /= supply;
    hitsAir /= supply;
  }
  return { round, supply, roles, air, hitsAir, bodies };
}
