"""End-to-end: `mecha visualize` on the fixture replays and live playback, driven in headless Chrome."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from .conftest import (
    BATTLE_ID,
    LOCAL_NAME,
    LOCAL_PLAYER,
    OPPONENT_NAME,
    LiveSession,
    Server,
    Tab,
    open_tab,
    wait_for_playback,
)

pytestmark = pytest.mark.e2e

# The fixture replays from the Local Player's side, newest first: (opponent, won, fight results as dot classes).
RECENT = [
    ("Nix", True, "wwwwww"),
    ("Mordekaiser", False, "lwllll"),
    ("miro", True, "wwwww"),
]
ROUNDS = 10
# Each fight dot's rendered colour as "w" (--win), "l" (--loss) or "?".
DOT_COLOURS = """dots => {
  const resolve = (name) => {
    const probe = document.createElement("i");
    probe.style.background = `var(${name})`;
    document.body.append(probe);
    const colour = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return colour;
  };
  const win = resolve("--win");
  const loss = resolve("--loss");
  if (win === loss) return "same colour for win and loss";
  return dots.map((d) => {
    const colour = getComputedStyle(d).backgroundColor;
    return colour === win ? "w" : colour === loss ? "l" : "?";
  }).join("");
}"""


def panel(tab: Tab, name: str) -> Any:
    return tab.page.locator(f'[data-panel="{name}"]')


def wait_ready(tab: Tab, *names: str) -> None:
    for name in names:
        tab.page.wait_for_selector(f'[data-panel="{name}"][data-state="ready"]', state="attached", timeout=20_000)


def stat(tab: Tab, key: str) -> str:
    return panel(tab, "record").locator(f'[data-stat="{key}"] .stat-value').inner_text().strip()


def games(tab: Tab) -> int | None:
    """The Record panel's game count, or None while it shows the empty note."""
    if panel(tab, "record").get_attribute("data-state") != "ready":
        return None
    return int(stat(tab, "games"))


def table_rows(tab: Tab, name: str) -> list[list[str]]:
    return (
        panel(tab, name)
        .locator("tbody tr")
        .evaluate_all("rows => rows.map(r => [...r.cells].map(c => c.innerText.trim()))")
    )


def store_json(tab: Tab) -> dict[str, Any]:
    """The store as plain JSON, minus the connection state."""
    data = tab.page.evaluate("() => JSON.parse(JSON.stringify(window.__visualizer.store.get()))")
    data.pop("connection", None)
    return data


def wait_points(tab: Tab, name: str, points: int) -> None:
    tab.page.wait_for_selector(f'[data-panel="{name}"][data-points="{points}"]', state="attached", timeout=20_000)


@pytest.fixture(scope="module")
def stats_tab(browser: Any, live_session: LiveSession) -> Any:
    tab = open_tab(browser, live_session.server.url)
    tab.page.evaluate("() => window.__visualizer.ui.view.set('stats')")
    wait_ready(tab, "record")
    yield tab
    tab.page.context.close()


@pytest.fixture(scope="module")
def finished(live_session: LiveSession) -> LiveSession:
    wait_for_playback(live_session.server)
    live_session.early.page.wait_for_function(
        "() => window.__visualizer.store.status.get()?.state === 'playback_done'", timeout=20_000
    )
    return live_session


# ---- setup ---------------------------------------------------------------------------------------------------


def test_setup_card_suggests_the_local_player_and_use_suggested_fills_stats(browser: Any, setup_server: Server) -> None:
    tab = open_tab(browser, setup_server.url)
    try:
        wait_ready(tab, "setup")
        setup = panel(tab, "setup")
        assert setup.is_visible()
        text = setup.inner_text()
        assert LOCAL_PLAYER in text
        assert LOCAL_NAME in text
        assert panel(tab, "record").get_attribute("data-state") == "empty"
        setup.locator('[data-action="use-suggested"]').click()
        wait_ready(tab, "record", "units", "specialists", "openings", "opponents", "recent", "history")
        assert games(tab) == 3
        assert not setup.is_visible()
        tab.assert_clean()
    finally:
        tab.page.context.close()


# ---- Stats view ----------------------------------------------------------------------------------------------


def test_record_is_exact(stats_tab: Tab) -> None:
    assert stat(stats_tab, "games") == "3"
    assert stat(stats_tab, "wl") == "2–1"
    assert stat(stats_tab, "winrate") == "67%"
    assert stat(stats_tab, "streak") == "W1"


def test_units_specialists_and_openings_have_plausible_rows(stats_tab: Tab) -> None:
    wait_ready(stats_tab, "units", "specialists", "openings")
    units = table_rows(stats_tab, "units")
    assert len(units) >= 5
    for name, fielded, pick, _ in units:
        # Names come from /catalog.json; none of the fixture's units are unknown.
        assert name and not name.startswith("Unknown unit"), name
        assert 1 <= int(fielded) <= 3
        assert pick.endswith("%")

    specialists = {row[0]: row[1:3] for row in table_rows(stats_tab, "specialists")}
    assert specialists == {"Supply Specialist": ["2", "1–1"], "Training Specialist": ["1", "1–0"]}

    openings = {row[0]: row[1:3] for row in table_rows(stats_tab, "openings")}
    assert openings == {"Crawler": ["2", "1–1"], "Arclight": ["1", "1–0"]}
    panel(stats_tab, "openings").locator('[data-group="name"]').click()
    exact = {row[0]: row[1] for row in table_rows(stats_tab, "openings")}
    assert exact == {
        "3 Crawler + 2 Sledgehammer": "1",
        "3 Crawler + 2 Tarantula": "1",
        "3 Arclight + 2 Sabertooth": "1",
    }
    panel(stats_tab, "openings").locator('[data-group="lead"]').click()


def test_recent_matches_fight_strips_match_the_replays(stats_tab: Tab) -> None:
    wait_ready(stats_tab, "recent")
    rows = panel(stats_tab, "recent").locator("tbody tr")
    assert rows.count() == len(RECENT)
    for index, (opponent, won, dots) in enumerate(RECENT):
        row = rows.nth(index)
        cells = row.locator("td")
        assert cells.nth(2).inner_text().strip() == opponent
        assert cells.nth(5).text_content().strip() == ("Win" if won else "Loss")
        strip = row.locator(".dot-strip i").evaluate_all("dots => dots.map(d => d.className).join('')")
        assert strip == dots, opponent
        assert row.locator(".dot-strip i").evaluate_all(DOT_COLOURS) == dots, opponent


def test_opponents_has_one_row_per_opponent(stats_tab: Tab) -> None:
    wait_ready(stats_tab, "opponents")
    rows = table_rows(stats_tab, "opponents")
    assert sorted(row[0] for row in rows) == ["Mordekaiser", "Nix", "miro"]
    assert all(row[1] == "1" for row in rows)


def test_history_chart_has_a_point_per_match(stats_tab: Tab) -> None:
    wait_points(stats_tab, "history", 3)


def test_mode_and_version_filters_change_the_counts(stats_tab: Tab) -> None:
    filters = panel(stats_tab, "filters")
    page = stats_tab.page
    try:
        filters.locator('[data-mode="async"]').click()
        page.wait_for_selector('[data-panel="record"][data-state="empty"]', state="attached")
        assert games(stats_tab) is None
        assert "No matches for these filters" in panel(stats_tab, "record").inner_text()
        filters.locator('[data-mode="normal"]').click()
        wait_ready(stats_tab, "record")
        assert games(stats_tab) == 3
        filters.locator('[data-mode="all"]').click()

        versions = filters.locator("[data-version]").evaluate_all("chips => chips.map(c => c.dataset.version)")
        assert sorted(versions) == ["2.0.0.4.2331", "2.0.0.5.2340", "all"]
        filters.locator('[data-version="2.0.0.5.2340"]').click()
        page.wait_for_function("() => document.querySelector('[data-stat=\"games\"] .stat-value')?.innerText === '1'")
        assert stat(stats_tab, "wl") == "1–0"
        assert len(table_rows(stats_tab, "recent")) == 1
        assert [row[0] for row in table_rows(stats_tab, "opponents")] == ["Nix"]
        filters.locator('[data-version="2.0.0.4.2331"]').click()
        page.wait_for_function("() => document.querySelector('[data-stat=\"games\"] .stat-value')?.innerText === '3'")
        filters.locator('[data-version="2.0.0.5.2340"]').click()
        page.wait_for_function("() => document.querySelector('[data-stat=\"games\"] .stat-value')?.innerText === '2'")
        assert stat(stats_tab, "wl") == "1–1"
    finally:
        filters.locator('[data-mode="all"]').click()
        filters.locator('[data-version="all"]').click()
    page.wait_for_function("() => document.querySelector('[data-stat=\"games\"] .stat-value')?.innerText === '3'")
    stats_tab.assert_clean()


# ---- Current Match view --------------------------------------------------------------------------------------


def assert_bars_sum_to_one(bars: Any, sides: tuple[str, ...]) -> None:
    for side in sides:
        bar = bars.locator(f'[data-bar="{side}"]')
        assert bar.count() == 1, side
        assert float(bar.get_attribute("data-total")) == pytest.approx(1.0, abs=0.002), side
        shares = bar.locator("[data-share]").evaluate_all("segs => segs.map(s => Number(s.dataset.share))")
        assert sum(shares) == pytest.approx(1.0, abs=0.002), side


def assert_current_match(tab: Tab, *, model_available: bool) -> None:
    page = tab.page
    page.wait_for_selector('[data-view-container="current"][data-active="true"]', state="attached", timeout=20_000)
    assert page.locator('[data-view-container="stats"]').get_attribute("data-active") == "false"
    wait_ready(tab, "match-header", "composition", "army-hp", "boards", "offer")

    header = panel(tab, "match-header")
    left = header.locator('[data-side="left"]')
    right = header.locator('[data-side="right"]')
    assert left.locator('[data-field="name"]').inner_text() == LOCAL_NAME
    assert right.locator('[data-field="name"]').inner_text() == OPPONENT_NAME
    assert left.locator('[data-field="rating"]').inner_text() == "1651"
    assert right.locator('[data-field="rating"]').inner_text() == "1179"
    assert header.locator('[data-field="round"]').inner_text() == str(ROUNDS)
    # The final fight takes the left core below zero; the header never shows negative HP.
    for side in (left, right):
        hp = side.locator('[data-field="hp"] .pstat-value').inner_text()
        assert "-" not in hp and "−" not in hp, hp
    assert left.locator('[data-field="hp"] .pstat-value').inner_text().split(" ")[0] == "0"

    win = panel(tab, "win-probability")
    if model_available:
        wait_points(tab, "win-probability", ROUNDS)
        assert win.get_attribute("data-model") == "available"
    else:
        assert win.get_attribute("data-model") == "unavailable"
        assert "Model unavailable" in win.inner_text()

    bars = panel(tab, "composition")
    assert_bars_sum_to_one(bars, ("left", "right"))
    # No fixture replay reaches round 10, so this round has no winning-board baseline yet...
    assert bars.locator('[data-bar="baseline-missing"]').count() == 1
    # ...but the whole-match view compares against the overall baseline.
    bars.locator('[data-scope="match"]').click()
    try:
        assert_bars_sum_to_one(bars, ("left", "right", "baseline"))
        assert "Winning boards, all rounds" in bars.locator('[data-bar="baseline"]').inner_text()
    finally:
        bars.locator('[data-scope="round"]').click()

    wait_points(tab, "army-hp", ROUNDS)
    # Round 0 (the opening frame, seen only by a tab connected before the match) isn't charted.
    rounds = page.evaluate(
        "() => Object.keys(window.__visualizer.store.match.get().rounds).map(Number).sort((a,b)=>a-b)"
    )
    assert [r for r in rounds if r >= 1] == list(range(1, ROUNDS + 1))

    cards = panel(tab, "offer").locator(".offer-card .card-name").all_inner_texts()
    assert len(cards) == 4
    assert all(not name.startswith("Card #") for name in cards), cards


def model_available(tab: Tab) -> bool:
    return bool(tab.page.evaluate("() => window.__visualizer.store.hello.get().modelAvailable"))


def test_early_tab_auto_switches_and_shows_the_match(finished: LiveSession) -> None:
    tab = finished.early
    assert tab.page.evaluate("() => window.__visualizer.store.frame.get().snapshot.match.battleId") == BATTLE_ID
    assert_current_match(tab, model_available=model_available(tab))
    tab.assert_clean()


def test_late_tab_rebuilds_the_match_from_the_catch_up(browser: Any, finished: LiveSession) -> None:
    tab = open_tab(browser, finished.server.url)
    try:
        assert_current_match(tab, model_available=model_available(tab))
        # The catch-up resends the latest fight_over frame; it must not add a duplicate point anywhere.
        assert len(tab.page.evaluate("() => window.__visualizer.store.predictions.get().rows")) in (0, ROUNDS)
        tab.assert_clean()
    finally:
        tab.page.context.close()


def test_reload_rebuilds_the_same_state(browser: Any, finished: LiveSession) -> None:
    tab = open_tab(browser, finished.server.url)
    try:
        assert_current_match(tab, model_available=model_available(tab))
        before = store_json(tab)
        tab.page.reload()
        tab.page.wait_for_function("() => window.__visualizer && window.__visualizer.store.hello.get()")
        assert_current_match(tab, model_available=model_available(tab))
        assert store_json(tab) == before
        # The early tab, fed incrementally, agrees with a fresh catch-up too.
        early = store_json(finished.early)
        for key in ("hello", "localPlayerId", "summaries", "baseline", "ratings", "status", "frame", "predictions"):
            assert early[key] == before[key], key
        # The early tab also saw round 0 (the opening); every charted round agrees.
        assert set(early["match"]["rounds"]) - {"0"} == set(before["match"]["rounds"])
        for round_number, entry in before["match"]["rounds"].items():
            assert early["match"]["rounds"][round_number]["army"] == entry["army"], round_number
            assert early["match"]["rounds"][round_number]["hp"] == entry["hp"], round_number
        tab.assert_clean()
    finally:
        tab.page.context.close()


@pytest.mark.parametrize("width", [1280, 1024])
@pytest.mark.parametrize("view", ["stats", "current"])
def test_layout_fits_without_horizontal_scroll(browser: Any, finished: LiveSession, width: int, view: str) -> None:
    tab = open_tab(browser, finished.server.url, width=width)
    try:
        page = tab.page
        page.evaluate(f"() => window.__visualizer.ui.view.set('{view}')")
        page.wait_for_selector(f'[data-view-container="{view}"][data-active="true"]', state="attached")
        wait_ready(tab, *(("record", "units", "recent") if view == "stats" else ("match-header", "army-hp")))
        page.wait_for_timeout(400)
        assert page.evaluate("() => document.documentElement.scrollWidth") <= width
        directory = os.environ.get("MECHA_E2E_SCREENSHOTS")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(directory) / f"e2e-{view}-{width}.png"), full_page=True)
        tab.assert_clean()
    finally:
        tab.page.context.close()


# ---- server --------------------------------------------------------------------------------------------------


def test_catalog_serves_every_unit(live_session: LiveSession) -> None:
    with urllib.request.urlopen(live_session.server.url + "catalog.json", timeout=10) as response:
        catalog = json.load(response)
    assert len(catalog["units"]) == 33
    assert catalog["units"]["15"]["name"] == "Arclight"
    assert catalog["roles"] == ["chaff", "chaffClear", "damage", "tank", "support", "unknown"]
