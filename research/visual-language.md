# Mechabellum visual language and game-art usage

Research for the Visualizer map, ticket `.scratch/visualizer/issues/02-research-visual-language.md`. Researched on 2026-10-23 against game build 2.0.x and the current Steam page.

## TL;DR

- **Look:** dark navy, near-black panels; one hot brand orange (`#FD9702`); blue for your side and red for the enemy. Text is condensed sans in white and grey-blue. Panels have chamfered corners, slanted plates, hexagon and diamond badges, and diagonal hatching stripes.
- **Fonts the game ships:** TextMeshPro SDF assets for **Akrobat** (Regular/Bold/Black) and **Xolonium** (Regular/Bold), plus **Roboto Condensed**, **Orbitron**, **Black Ops One** and **BigNoodleTitling**. Free equivalents: Xolonium and Akrobat are both free to self-host. On Google Fonts, Orbitron, Roboto Condensed and Black Ops One are available as-is, and Saira Semi Condensed or Barlow Semi Condensed stand in for Akrobat.
- **Art usage:** nothing grants permission. Every image is "owned by the applicable game studio". The Dreamhaven User Agreement forbids copying, derivative works and extracting data from the game "except as expressly provided". There is no fan-content policy. Community norm: wiki.gg, MechaMonarch, Tiermaker and GamePressure all show unit icons openly, and no takedowns are known. **Recommendation:** commit no game art to the repo or package. Fetch wiki.gg icons at runtime into a local cache on the user's machine, with a text/glyph fallback. Never pull icons out of the game files. Don't use the Mechabellum logo.

## 1. Colour palette

Source: colours sampled (median-cut quantisation over UI regions) from the official Steam store screenshots listed in section 6. JPEG compression shifts values by a few points, so treat these as design tokens, not exact game constants.

### Backgrounds and surfaces

| Token | Hex | Where seen |
|---|---|---|
| `bg-void` | `#050608` | outer screen frame, menu edges (ss7) |
| `bg-base` | `#0E0F18` | main menu panel base (ss7) |
| `bg-panel` | `#151521` / `#1A1A26` | panel fill (ss7) |
| `bg-nav` | `#1B1F33` | top nav bar (ss7) |
| `surface-row` | `#222943` → `#2A3350` | tech list rows, navy (ss6) |
| `surface-row-deep` | `#151B2E` | row shadow / inset (ss6) |
| `tab-active` | `#2E4475` (menu: `#1D3E6F`) | selected tab (ss6, ss7) |
| `tab-inactive` | `#1A2344` | unselected tab (ss6) |
| `button` | `#1B2552` fill, `#47548D` edge | BACK / HIDE UI buttons (ss6) |
| `hud-plate` | `#191A22` / `#393434` | in-match plates over terrain (ss4); they are translucent |

### Text and icons

| Token | Hex | Where seen |
|---|---|---|
| `text-primary` | `#F0F0F0` | headings, values |
| `text-secondary` | `#8F9AB8` (alt `#8896B6`) | nav labels, sub-tabs (ss7) |
| `icon-line` | `#AFCDFF` | stat icons, line glyphs (ss6) |

### Accents

| Token | Hex | Where seen |
|---|---|---|
| `accent` (brand orange) | `#FD9702` (alt `#F99F06`) | logo (ss1) |
| `accent-hud` | `#F7A111` / `#EE9900` | ability buttons, supply value (ss3) |
| `accent-gold` | `#D5910C` | COST label, coin icon (ss6) |
| `accent-deep` | `#98621C` | progress-bar fill (ss7) |
| `accent-bg` | `#55330A` | orange button background (store cart, ss7) |
| `highlight` | `#FFC34B` | Quick Deploy checkbox (ss4) |
| `xp` | `#406F9B` | player XP bar (ss7) |

### Team colours

| Token | Hex | Where seen |
|---|---|---|
| `team-self` | `#3E5EB0` (gradient `#354899` → `#4E88CE`) | left score bar, your side (ss4) |
| `team-enemy` | `#AA3539` (gradient `#8D2E33` → `#BC4345`) | right score bar, opponent (ss4) |
| `cost-tag` | `#83151C` / `#631617` | red cost chip on unit cards (ss3) |

Rule seen in every match screenshot: **you are blue on the left, the opponent is red on the right**. Mechs are painted the same way (ss1, ss2). Orange belongs to the brand and to "actionable / currency"; it is never a team colour.

## 2. Typography

Source: a read-only string scan of the font names inside the installed game's `Mechabellum_Data/resources.assets`, `globalgamemanagers.assets`, `sharedassets1.assets` and `level0`. No assets were extracted.

| Font found in game | Role (matched against screenshots) | Licence | Free / web substitute |
|---|---|---|---|
| **Akrobat** Regular / Bold / Black (`Akrobat-* SDF`) | main UI body: stat labels (COST, HP, SPEED), unit names, list items. Condensed, uppercase-friendly | Fontfabric, "Free for commercial and personal use" ([fontfabric.com/fonts/akrobat](https://www.fontfabric.com/fonts/akrobat/)) | self-host Akrobat, or Google **Saira Semi Condensed** / **Barlow Semi Condensed** |
| **Xolonium** Regular / Bold (`Xolonium-* SDF`) | techno display: nav tabs (SEASON, MULTIPLAYER), "Round 8", score numerals, buttons | SIL OFL 1.1 since v3.1, also GPL-2+ with font exception ([fontlibrary.org/font/xolonium](https://fontlibrary.org/font/xolonium), [Debian copyright](https://metadata.ftp-master.debian.org/changelogs/main/f/fonts-xolonium/unstable_copyright)) | self-host Xolonium, or Google **Orbitron** / **Exo 2** |
| Roboto Condensed (Light → Bold, plus italics) | secondary UI text | Apache 2.0 (Google Fonts) | **Roboto Condensed** as-is |
| Orbitron (Light, Medium, Bold, Black) | display | OFL (Google Fonts) | **Orbitron** as-is |
| Black Ops One | stencil-ish display | OFL (Google Fonts) | **Black Ops One** as-is. It is close to the blocky logo wordmark, but don't imitate the logo |
| BigNoodleTitling | titling | freeware (James Arboghast) | **Bebas Neue** |
| Source Han Sans SC, YouSheBiaoTiHei | Chinese localisation | — | Noto Sans SC |

Suggested Visualizer stack:

- display: `"Xolonium", "Orbitron", sans-serif`
- body: `"Akrobat", "Saira Semi Condensed", "Roboto Condensed", sans-serif`
- numbers: Xolonium or Orbitron with `font-variant-numeric: tabular-nums`

## 3. Iconography

- **Monochrome line glyphs** in white or `#AFCDFF` on navy for stats (HP, speed, ATK, range, splash, interval, target). They are small, about 16 px on the wiki (`File:HP.png`, `File:Speed.png`, and so on).
- **Filled orange glyphs** on dark-orange tiles for active abilities and specialist cards (ss3). Grey versions of the same glyphs mean used or locked.
- **Unit cards:** a square portrait tile (rendered mech art on a dark background) with a **cost chip in the bottom-left corner**: red for one side, brown-orange for the other (ss3).
- **Badges:** a hexagon holds the unit level number (ss3, "1"), diamonds mark tech levels 1/2/3 (ss6), and a shield-chevron shape shows rank (Diamond II, ss7).
- **Currency:** a hexagonal orange coin glyph (supply/cost) is used everywhere a price appears.
- **Navigation:** double chevrons `«` `»` for paging (ss6, ss7).

## 4. Panel and frame shapes

- **Chamfered corners:** panels and buttons cut one or two corners at 45°. Rounded corners are not used. CSS: `clip-path: polygon(...)` with an 8 to 12 px cut.
- **Slanted plates:** the in-match top bar is a trapezoid plate per player. The score bar slants and mirrors left/right, with the name under it (ss3, ss4).
- **Thin bright borders:** a 1 px light-blue or grey-blue edge (`#47548D`) on navy fills. Selected tabs get a brighter fill plus an underline glow (ss7).
- **Diagonal hatching:** section headers carry a strip of 45° stripes, e.g. "Equipped Tech" in ss6. Reproduce with `repeating-linear-gradient(135deg, ...)`.
- **Metallic bevel frames:** only around player portraits in the screen corners (ss3, ss4, ss7). This is a 3D-rendered texture, so imitate it with a gradient border; don't copy it.
- **Translucency:** match HUD plates are semi-transparent over the battlefield. Menus are opaque.

## 5. HUD conventions

From ss3 and ss4:

- **Top bar, mirrored:** self on the left (portrait, blue score bar, name) and opponent on the right (red bar, name, portrait). A centre pill shows `Round N`, a timer and a spectator count.
- **Side columns:** each player's unit cards in a 2-column grid of portrait tiles with cost chips. The supply total sits at the bottom (`100` with coin glyph).
- **Unit detail panel** (bottom left): unit name, subtitle ("Light High Damage Unit"), stat rows of icon + value, and a wireframe render of the unit.
- **Bottom-right control cluster:** round selector, pause, speed `− 2.0 +`, Quick Deploy checkbox.
- **Battlefield markers:** small cyan/white glyphs (stars, upgrade arrows in yellow, tech icons) float over units.

For the Visualizer this means: mirror self (blue, left) vs opponent (red, right); keep round and time centred; put numbers in the display face; and set cost/supply in orange with the coin glyph.

## 6. Motion

Motion can't be verified from stills. The only official motion source is the trailers (below), and they were not frame-analysed for this note. Treat any motion spec as a design choice, not a finding. A cautious default that fits the static language: short (150–200 ms) linear slides and fades, a glow pulse on the active round or alert, and bars that fill left to right. Avoid bouncy easing.

## 7. Reference material

**Steam store** (app 669330; developer Game River, publisher Dreamhaven, per the [Steam appdetails API](https://store.steampowered.com/api/appdetails?appids=669330)):

- [ss1 hero mechs](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/57f953a6613e712f6f80300c5acbad080566d5c8/ss_57f953a6613e712f6f80300c5acbad080566d5c8.1920x1080.jpg): logo colours, blue vs red mechs
- [ss2 battle](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/e3ae4e6a6d7eed84de8375fa8f76c5a417381e94/ss_e3ae4e6a6d7eed84de8375fa8f76c5a417381e94.1920x1080.jpg)
- [ss3 1v1 match HUD](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/6b34d114c6c2d2b8aaafe6d44f1a7cbbb9cd8f03/ss_6b34d114c6c2d2b8aaafe6d44f1a7cbbb9cd8f03.1920x1080.jpg): **best HUD reference**
- [ss4 2v2 match HUD](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/142e795328a8677cd8e8efbb13a49562a31afcf7/ss_142e795328a8677cd8e8efbb13a49562a31afcf7.1920x1080.jpg): team score bars, speed controls
- [ss5](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/95b60f57c532ae403b30be039eacc6fd5d761c95/ss_95b60f57c532ae403b30be039eacc6fd5d761c95.1920x1080.jpg)
- [ss6 unit detail / tech panel](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/3b53d00a199f200c6bbb8dd71bf07f0ae01f3cc0/ss_3b53d00a199f200c6bbb8dd71bf07f0ae01f3cc0.1920x1080.jpg): **best panel/list reference**
- [ss7 season menu](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/cedea234e5dc4d68c65194bc4a4dd02971ec4762/ss_cedea234e5dc4d68c65194bc4a4dd02971ec4762.1920x1080.jpg): **best menu/nav reference**, progress bar
- [ss8](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/33ef79ff2a50d0851a6a7dca5a142a0d57c3d961/ss_33ef79ff2a50d0851a6a7dca5a142a0d57c3d961.1920x1080.jpg), [ss9](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/76a99edc02f4a8d829a5e9ed489fadeff32e35c3/ss_76a99edc02f4a8d829a5e9ed489fadeff32e35c3.1920x1080.jpg)
- [Header capsule](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/845165412668d8b6765b3fa19639ea7c5b1d892c/header_alt_assets_2.jpg), [page background](https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/669330/102c5fff389243dde7739ece2c6d187bd7571305/page_bg_raw.jpg)

**Trailers:** "Mechabellum 2.0" (on the Steam page) and [Season 8 trailer](https://youtu.be/1fk1-CQgxYE).

**Official press kit:** [dhvn.gg/mbpresskit](https://dhvn.gg/mbpresskit) redirects to a [Google Drive folder](https://drive.google.com/drive/folders/1JfRIfYbDnYarWml74I5QIXtBMdKW7fyG) with Key Art, Logos, Fact Sheet, Press Releases, Screenshots, Season 6/7/8 and Trailer folders. It holds no unit icons and no usage guidelines. Linked from the [Season 8 press release](https://pressreleases.triplepointpr.com/2026/06/09/dreamhaven-and-game-river-launch-mechabellum-season-8-on-steam-and-the-epic-games-store/).

**Official sites:**

- `mechabellum.com` is an "Under Construction" page.
- The `website` field on Steam is `playmechabellum.com`, which redirects to [store.dreamhaven.com/mechabellum](https://store.dreamhaven.com/mechabellum). Neither has design tokens or a fan policy.

**Wiki:** [mechabellum.wiki.gg](https://mechabellum.wiki.gg/wiki/Mechabellum_Wiki). For example, [Fang](https://mechabellum.wiki.gg/wiki/Fang) uses:

- unit icons named `<id>_<中文>_<Name>_Icon_1.png`, e.g. `9_尖牙_Fang_Icon_1.png`
- tech icons such as `Ignite.png`
- 16 px stat icons such as `Cost.png` and `HP.png`

The numeric prefix looks like the game's unit id, which could help map round-2 id tables to icons. That is unverified and worth checking against the id tables.

## 8. May a local fan tool show unit icons or art?

### What the sources say

1. **Developer/publisher terms.** The Dreamhaven **User Agreement** (2025-07-28, [dhvn.gg/legal](https://dhvn.gg/legal) → account.dreamhaven.com/legal/…) grants a licence "for your personal, non-commercial entertainment purposes only". Its *License Limitations* bar users from:
   - (b) "copy, modify, … or create derivative works … of the Platform or Game(s), or any part thereof (except as expressly provided by Dreamhaven)"
   - (c) "incorporate the … Game(s) or any part thereof in, any other programs"
   - (e) "attempt to extract or otherwise derive source code or other data from the … Game(s)"

   Its *Ownership* clause reserves all IP. Mechabellum is a Game River game, so it may count as a "Partner Game" with its own Partner Agreement. None was found: the Steam EULA slot `669330_eula_0` fails to load, and no Game River EULA is published. Either way, **there is no express permission** for fan use of art.
2. **No fan-content policy.** None was found from Game River or Dreamhaven, unlike Epic, Supercell or Jagex, which publish one.
3. **Mod stance** ([wiki Mod page](https://mechabellum.wiki.gg/wiki/Mod), quoting Community Manager Mivo on Discord, 13 Oct 2026):
   - client-side QoL mods are used "at the player's own risk"
   - "Mods that send data to the server are not allowed and bannable"

   It says nothing about art. A dev reply on [Steam](https://steamcommunity.com/app/669330/discussions/0/581684714276085190/) thanks modders and says the team is building similar features.
4. **Wiki licence.** wiki.gg text is CC BY-SA 4.0, but each game image's file page (e.g. [File:Cost.png](https://mechabellum.wiki.gg/wiki/File:Cost.png)) says "This file is owned by the applicable game studio and/or its licensors" and carries an *In Copyright* badge. **The wiki does not relicense icons.**
5. **Community norm.** The wiki itself shows unit icons, and so do the fan site MechaMonarch ([Steam announcement](https://steamcommunity.com/app/669330/discussions/0/3810655600549486766)), [Tiermaker](https://tiermaker.com/create/mechabellum-units-083-17347502) and [GamePressure](https://www.gamepressure.com/S013-amp.asp?ID=22075). No takedowns or objections were found. Showing official art in non-commercial fan resources is tolerated, not licensed.

### Verdict

**Not expressly allowed; tolerated in practice.** For a local, non-commercial tool that runs only on the player's own machine, showing unit icons is in line with what the community already does and is low-risk. Two things make it riskier:

- **Bundling or redistributing the art.** Committing PNGs to this repo or shipping them inside the Python package is redistribution and copying under clause (b). The repo carries its own `LICENSE.md`, which would wrongly suggest the art is covered.
- **Extracting art from the game files.** Pulling art out of `Mechabellum_Data` (AssetStudio or similar) is the "extract … data from the Game" that clause (e) forbids.

### Recommended sourcing, in order

1. **Runtime fetch from wiki.gg into a user-local cache** (e.g. `~/.cache/mecha/icons/`), with the `File:` page as provenance and a credit line ("Unit art © Game River; via mechabellum.wiki.gg"). No art goes into git or the wheel. Throttle requests and set a descriptive User-Agent.
2. **Fallback that needs no art:** unit name plus a monochrome generic glyph or initials tile in the house style. This must exist anyway for offline use and for new units the wiki hasn't added yet.
3. **Press kit:** fine for screenshots/key art in a design mock-up. It has no unit icons, so it is no help for per-unit tiles.
4. **Avoid:** extracting icons from the game install, and using the Mechabellum logo/wordmark, which is a trademark and would imply endorsement. Use an original "Visualizer" wordmark in the same colours instead.

If the tool is ever published beyond personal use, ask Game River/Dreamhaven for written permission. Contacts: mail@mechabellum.com, or the official Discord ([discord.gg/mechabellum](https://discord.com/invite/mechabellum)).

## Open questions

- Is there a Game River Partner Agreement or in-game EULA? It may be shown at first launch or in the game's settings. Not checked in-client.
- Do the wiki icon prefixes (`9_…Fang`) match the round-2 unit id tables?
- Motion: frame-check the 2.0 trailer if the prototype needs animation detail.
