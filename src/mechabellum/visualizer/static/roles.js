// Unit names and roles for the browser, loaded from the server's `GET /catalog.json` (built from `unit_roles.json`
// and `collector/unit_catalog.py`). The server owns the composition maths; this table only names units and colours
// their chips. A unit missing from the catalog is "unknown". Call `loadCatalog()` once before mounting panels.

export const ROLES = ["chaff", "chaffClear", "damage", "tank", "support", "unknown"];

export const ROLE_LABELS = {
  chaff: "Chaff",
  chaffClear: "Chaff clear",
  damage: "Damage",
  tank: "Tank",
  support: "Support",
  unknown: "Unknown",
};

// {id: {name, primary, secondary, air, hitsAir, members}}. Empty until the catalog loads; if the fetch fails it
// stays empty, so every unit shows as "Unknown unit (<id>)" rather than breaking the page.
let UNITS = {};

export async function loadCatalog(url = "/catalog.json") {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    UNITS = data && typeof data.units === "object" ? data.units : {};
  } catch (err) {
    console.warn("Visualizer: unit catalog unavailable; units show as unknown.", err);
    UNITS = {};
  }
  return UNITS;
}

export function unitInfo(id) {
  const row = UNITS[id];
  if (!row) {
    return { id, name: `Unknown unit (${id})`, primary: "unknown", secondary: null, air: false, hitsAir: false, members: 1 };
  }
  const primary = ROLES.includes(row.primary) ? row.primary : "unknown";
  return { id, name: row.name, primary, secondary: row.secondary ?? null, air: !!row.air, hitsAir: !!row.hitsAir, members: row.members || 1 };
}

export function unitName(id, fallback) {
  return UNITS[id] ? UNITS[id].name : fallback || `Unknown unit (${id})`;
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
