# Unit roles for the board-composition view

Question (ticket `.scratch/visualizer/issues/08-research-unit-roles.md`): which role taxonomy should the
Current Match view use to show what share of a board is chaff, damage, tank and so on, which role does each
of the 33 units in `collector/game_names.json` `unitPrices` get, and what should "share of board" be
weighted by?

Researched 2026-10-24. Game data is from 2.0.0.4; the wiki already lists a 2.0.0.5 patch (23.10.2026).

## Answer in short

- **Five roles that split the board, plus two flags that don't.** The roles are Chaff, Chaff clear, Damage,
  Tank and Support. Every unit gets exactly one primary role, so the shares add up to 100%. The flags are
  **Air** (the unit flies) and **Hits air** (it can shoot air units). They are separate yes/no facts taken
  straight from the game config, so they don't take up a slice of the bar.
- **One primary role per unit, plus an optional secondary role.** About half the units are judgement calls
  that players use in two roles. Only the primary role goes into the share bar. The secondary role belongs
  in the tooltip and in the table below, which leaves room to try a 50/50 split later.
- **Weight by supply value**: each unit's `sell_supply` from the snapshot. Do not weight by unit count or
  member count. The repo already uses this as a board's value (`features/position.py:278`,
  `features/geometry.py:66`).

## Sources

- **Game config**: [qbisi/mechcore @ b2c7804](https://github.com/qbisi/mechcore/tree/b2c7804ae50e84a3113c36e359c913de4344d721/config)
  (game 2.0.0.4.2331). This is the commit pinned in `game_names.json` `sources.primary`, written by
  `scripts/build_game_names.py`. The values come from `config/units/<unit>.yaml`:
  `formation.members`, `domain`, `size`, `max_life`, `attack.{base_damage, timing.interval, range,
  splash_radius, targets, melee}`, `path.count`, `weapons.per_skill`. Supply comes from `unit_prices.yaml`,
  through `game_names.json`.
- **Community vocabulary**: the [mechabellum.wiki.gg Terminology page](https://mechabellum.wiki.gg/wiki/Category:Terminology)
  defines *Chaff*, *Chaff Clear*, *DPS* and *AA* and gives example units for each. Each unit's wiki page
  (`https://mechabellum.wiki.gg/wiki/<Unit>`) describes its role. Most were edited for patches 2.0 to
  2.0.0.5 (Sept–Oct 2026).
- **Guide**: [finalboss.io beginner guide](https://finalboss.io/mechabellum-beginner-guide-to-unit-roles-deployment-and)
  (7/8/2026). It names three core roles, *chaff*, *chaff clear* and *carry*, plus two "functional tags",
  *tank* and *anti-air*. It doesn't say which units fill which role.
- Steam discussion threads only gave scattered opinions (Fang as AA and chaff, Marksman as early AA), which
  agree with the wiki. Reddit and YouTube were not used.

## What the community says

The wiki's Terminology page has the clearest definitions, and they match the guide:

- **Chaff**: "Cannon fodder units. Typically, swarm units with high squad count and low cost." Its
  examples are Crawler, Fang, Hound, Sledgehammer, Mustang, Steel Ball and Wasp.
- **Chaff Clear**: "Units that are able to quickly clear chaff units efficiently." Its examples are Vulcan,
  Hound, Fire Badger, Wraith, Arclight, Typhoon and Tarantula. Mustang and Sledgehammer count too
  "depending on tech".
- **DPS**: the average damage dealt over time, and also the units whose main job is dealing damage. The
  guide calls this role *carry*. Unit pages use "anti-big" or "the bane of all high HP units" for the
  single-target killers (Steel Ball, Melting Point, Scorpion, Void Eye).
- **AA**: "units that have the inherent ability to attack air units". The game config holds this exact
  fact as `attack.targets.air`.
- **Tank**: the Terminology page doesn't define it. Unit pages use it often: Sledgehammer, Sabertooth and
  Tarantula are each called a "Heavy Tank" or "tank", and Fortress, Rhino, Mountain and Vortex as tank
  with a tech.

Two things stand out. First, the wiki's example lists overlap: Hound, Mustang and Sledgehammer are each
listed as both chaff and chaff clear. Second, most unit pages describe two or three roles that depend on
tech. So any single label is a simplification, and community usage supports a primary role plus a
secondary one.

## What the game config does and doesn't give us

The config has **no role or class field**. It does have facts that support the roles:

- `attack.targets.air`: true for 14 of the 33 units. This is the AA flag, with no guesswork.
- `domain: air`: true for 7 units (Wasp, Overlord, Phoenix, Wraith, Phantom Ray, Raiden, Abyss).
- `formation.members` and supply give bodies per 100 supply, which separates chaff (Crawler 24, Fang 18
  and Wasp/Mustang 6 per 100 supply) from everything else (2 or fewer).
- `max_life × members / supply` gives HP per 100 supply, which separates tanks. Mountain (17.1k),
  War Factory (14.2k), Sandworm (12.2k) and Fortress (11.0k) lead. Rhino, Sledgehammer, Steel Ball and
  Vortex sit between 8.5k and 9.6k.
- `splash_radius` greater than 0 marks most chaff-clear units: Vulcan and Scorpion 15, Arclight 7 (and it
  chains), Fire Badger 7, Wraith 8, Typhoon 5 with a high fire rate.

Rough DPS per 100 supply, worked out from base damage, interval and shot count, is not reliable enough to
assign roles. The laser units (Steel Ball, Melting Point) ramp up to 47× damage through
`damage_multipliers`. Arclight's chain, Hacker's control beam and every `extra_weapons` tech fall outside a
simple formula. The numbers below are level-1 values with no techs, there only to back up the judgement.

## Recommended taxonomy

| Role | Meaning | Main evidence |
| --- | --- | --- |
| **Chaff** | Cheap bodies that soak fire and pull aggro | wiki *Chaff*; at least 6 bodies per 100 supply |
| **Chaff clear** | Splash or multi-target damage that kills swarms | wiki *Chaff Clear*; `splash_radius`, multi-shot |
| **Damage** | Single-target or high-burst damage, the "carry" or "anti-big" units | wiki *DPS*; guide *carry* |
| **Tank** | High HP per supply in the front line, absorbing damage for the carries | guide *tank* tag; HP per 100 supply |
| **Support** | Utility instead of damage or HP: control, healing, recon | Hacker, Farseer pages |

Flags shown next to the roles, not inside the share bar:

- **Air**: `domain == air`.
- **Hits air**: `attack.targets.air`. This is the "how much AA do I have" figure, best shown as its own
  supply share compared with winning boards that faced air.

Why Air and AA aren't roles: they cut across the five roles. Wasp is air chaff, Abyss is air damage and
Marksman is ground damage that hits air. Putting them in the bar would mean either double-counting units
or dropping their real role. They are also the only two facts the config states exactly, so there's no
judgement to make.

## Unit → role table

Fit: **clean** means the wiki, guides and config stats agree. **judgement** means players use the unit in
more than one role, or the sources disagree. HP/100 and DPS/100 are level-1 values per 100 supply, worked
out from mechcore.

| id | Unit | Primary | Secondary | Air | Hits air | Fit | Supply | Members | HP/100 | DPS/100 | Notes |
| --: | --- | --- | --- | :-: | :-: | --- | --: | --: | --: | --: | --- |
| 1 | Fortress | Tank | Damage | | | judgement | 400 | 1 | 10984 | 1812 | wiki: "tanky giant with high damage weaponry"; both stats high |
| 2 | Marksman | Damage | | | ✓ | clean | 100 | 1 | 1622 | 751 | range 140, single target; early AA |
| 3 | Vulcan | Chaff clear | Tank | | | clean | 400 | 1 | 7570 | 375 | wiki chaff-clear list; splash 15, fire |
| 4 | Melting Point | Damage | | | ✓ | clean | 400 | 1 | 7727 | (ramps) | "bane of all high HP units"; ramping laser |
| 5 | Rhino | Damage | Tank | | | judgement | 200 | 1 | 9648 | 3956 | wiki: "tank and/or a DPS unit"; melee |
| 6 | Wasp | Chaff | Damage | ✓ | ✓ | judgement | 200 | 12 | 1866 | 866 | wiki chaff list; also a swarm air carry |
| 7 | Mustang | Damage | Chaff | | ✓ | judgement | 200 | 12 | 2058 | 540 | unit page "main DPS" and AA; Terminology lists it as chaff |
| 8 | Steel Ball | Damage | Chaff | | | judgement | 200 | 4 | 9142 | (ramps) | "bane of all high HP units"; Terminology lists it as chaff |
| 9 | Fang | Chaff | Damage | | ✓ | clean | 100 | 18 | 2106 | 756 | "chaff" or "ranged DPS" depending on tech |
| 10 | Crawler | Chaff | | | | clean | 100 | 24 | 6000 | 3160 | "the most efficient chaff unit" |
| 11 | Overlord | Damage | Chaff clear | ✓ | ✓ | clean | 500 | 1 | 4268 | 1649 | air giant, large splash |
| 12 | Stormcaller | Chaff clear | Damage | | | judgement | 200 | 4 | 2298 | 1872 | long-range splash artillery; also snipes towers |
| 13 | Sledgehammer | Tank | Chaff | | | judgement | 200 | 5 | 8695 | 338 | unit page "heavy tank"; Terminology lists it as chaff |
| 14 | Hacker | Support | | | | clean | 200 | 1 | 1624 | — | takes control of enemies "instead of dealing damage" |
| 15 | Arclight | Chaff clear | | | | clean | 100 | 1 | 4813 | 406 (chains) | wiki chaff-clear list |
| 16 | Phoenix | Damage | | ✓ | ✓ | clean | 200 | 2 | 1491 | 828 | air, high single hit |
| 17 | War Factory | Tank | Damage | | | judgement | 800 | 1 | 14199 | 522 | titan, produces units; wiki gives no role |
| 18 | Wraith | Chaff clear | Tank | ✓ | ✓ | clean | 300 | 1 | 4705 | 79 (+techs) | "strong chaff clear"; "a tanky air unit" |
| 19 | Scorpion | Damage | Tank | | | clean | 300 | 1 | 6211 | 789 | anti-big; "inefficient" against small units |
| 20 | Fire Badger | Chaff clear | | | | clean | 200 | 3 | 6333 | 405 | wiki chaff-clear list; flamethrower |
| 21 | Sabertooth | Tank | Damage | | | judgement | 200 | 1 | 7071 | 2043 | unit page "Heavy Tank" with anti-medium damage |
| 22 | Typhoon | Chaff clear | Support | | ✓ | judgement | 300 | 2 | 6353 | 587 | "small ground and air targets"; also strong AA; Maintenance Array heals |
| 23 | Sandworm | Damage | Tank | | | judgement | 400 | 1 | 12161 | 973 | burrowing melee; wiki: "cannot consistently tank" |
| 24 | Tarantula | Chaff clear | Tank | | | judgement | 200 | 1 | 7017 | 413 | "medium-ranged tank" and "pure chaff-clear" |
| 25 | Phantom Ray | Damage | Chaff clear | ✓ | ✓ | judgement | 200 | 3 | 5118 | 1087 | "high DPS"; chaff clear when paired with Badger |
| 26 | Farseer | Support | Damage | | ✓ | judgement | 300 | 1 | 3997 | 449 | wiki: DPS or "a more supportive role" |
| 27 | Raiden | Chaff clear | Damage | ✓ | ✓ | judgement | 400 | 1 | 4016 | 273 | "excels at clearing squads of medium units" |
| 28 | Hound | Chaff clear | Chaff | | | judgement | 100 | 5 | 4395 | 512 | Terminology lists it in both chaff and chaff clear |
| 29 | Abyss | Damage | | ✓ | ✓ | clean | 800 | 1 | 8369 | 121 (beam) | "the perfect weapon against other large units" |
| 30 | Void Eye | Damage | | | | clean | 100 | 3 | 4110 | 1040 | "high-DPS burst damage unit" against heavy targets |
| 31 | Vortex | Tank | Damage | | | judgement | 100 | 1 | 8538 | 872 | "robust, low-cost frontline" that kills medium units |
| 32 | Centurion | Damage | Tank | | ✓ | clean | 300 | 1 | 5500 | 1744 | "high damage single target"; sometimes tank |
| 2002 | Mountain | Tank | Damage | | | clean | 800 | 1 | 17082 | 369 (+techs) | highest HP per supply in the game |

Primary-role counts: Chaff 3, Chaff clear 9, Damage 13, Tank 6, Support 2. 16 units are clean and 17 are
judgement calls. Every judgement-call unit has a secondary role, so one role is not enough for those 19.
Most clean units have one too, but for them the primary role clearly dominates.

The table leaves out ids that `unitPrices` doesn't have: Larva (1001, from Sandworm) and Spider Mine (1002,
from Tarantula) spawn during battle, so they never sit on a board. Death Knell has a wiki page but no 2.0.0.4
price.

## Weighting: supply value

| Weighting | What it shows | Problem |
| --- | --- | --- |
| Unit count | One Crawler squad equals one Mountain | 100 supply counts the same as 800, so a board of 100-supply units looks huge |
| Member count | Bodies on the field | Crawler 24 and Fang 18 swamp everything, so every board looks like chaff |
| **Supply value** | Where the player spent their supply | None worth worrying about; this is the decision the player actually makes |

Supply value is the right choice. The view compares a board with **winning boards**, and the thing a player
can change is how they split supply between roles. The game's own `SellSupply` on each unit already
includes level-ups (and possibly techs; this is unverified). It is in every snapshot as `unit.sell_supply`,
and the repo already sums it as army value (`features/position.py:278`), so the new view will match the
existing features.

Member count is still worth showing as a secondary figure for Chaff only, as "bodies". Chaff is about
targets, not value: 200 supply of Crawlers is 48 bodies, while 200 supply of Sledgehammers is 10.

## Caveats

- **The roles depend on tech.** Most judgement calls change with one tech: Mustang with or without Aerial
  Specialization, Tarantula with High-Explosive Ammo or Mechanical Rage, Fang chaff or DPS, Sledgehammer with
  Mechanical Rage. A static table can't follow these changes. If the view later wants to be accurate, the
  hook is the `active_technologies` per unit that snapshots already carry, so specific techs could override
  the role. That would need its own table.
- **Version drift.** The config is 2.0.0.4, but the wiki already shows 2.0.0.5 changes (Centurion, Vortex,
  Sledgehammer tech prices). A balance patch moves the stats but rarely the roles. Review the table when
  `build_game_names.py` moves to a new mechcore commit.
- **Many wiki pages carry text from before 2.0** (for example the Fortress, Stormcaller, Scorpion, Farseer,
  Steel Ball and War Factory pages, last edited for 1.11.x). Their role descriptions are probably still
  right, but nothing confirms that for 2.0.
- **Not checked against Reddit or YouTube.** Streamer usage (for example Mustang as chaff or as DPS) may
  differ from the wiki. The judgement-call rows are where that matters.
- **The config stats are level-1 values with no techs**, and the DPS column ignores ramping lasers, chains
  and extra weapons. Use it as a sanity check, not as a way to derive roles.
- **What `SellSupply` covers is unverified**: whether it is exactly what was invested, including techs and
  levels, or a refund value. Check it against a few known boards before treating it as invested supply.
- **Chaff will look small when weighted by supply** (only 3 primary units, all cheap). That is accurate,
  because chaff is cheap. Keep it in mind when choosing the scale of the comparison bar.
