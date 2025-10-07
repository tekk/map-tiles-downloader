from __future__ import annotations

import asyncio
import os
import time
import locale
import random
from typing import Optional, Tuple, Dict, List, Any
import aiohttp
from pathlib import Path

# Import curses conditionally for cross-platform compatibility
try:
    import curses

    HAS_CURSES = True
except ImportError:
    curses = None  # type: ignore
    HAS_CURSES = False

from .providers import PROVIDERS, get_url_builder
from .regions import load_region_catalog
from .tiling import count_tiles_for_regions, lon2tilex, lat2tiley
from .downloader import TileDownloader, TileRequest
from .tiling import iter_tiles_for_bbox


class Menu:
    def __init__(
        self,
        stdscr: Any,
        title: str,
        choices: List[str],
        multi: bool = False,
        all_toggle: bool = False,
        hierarchical_all: bool = False,
        colors_enabled: bool = True,
        allow_back: bool = False,
    ):
        self.stdscr = stdscr
        self.title = title
        self.choices = choices
        self.multi = multi
        self.all_toggle = all_toggle
        self.hierarchical_all = hierarchical_all
        self.colors_enabled = colors_enabled
        self.allow_back = allow_back
        self.current = 0
        self.selected: Dict[int, bool] = {}
        self.top = 0  # index of first visible item for scrolling

    def _get_display_selected(self, idx: int) -> bool:
        """Get whether an item should be displayed as selected, considering hierarchical relationships."""
        if not self.multi:
            return self.selected.get(idx, False)

        # Handle global "All ..." toggle
        if self.all_toggle and idx == 0:
            return all(
                self.selected.get(i, False)
                for i in range(1, len(self.choices))
                if len(self.choices) > 1
            )

        # Handle hierarchical "All of X" items
        if self.hierarchical_all and idx > 0:  # Skip the global "[All ...]" item
            choice = self.choices[idx]
            if " / All of " in choice:
                # This is an "All of Country" item, check if all regions for this country are selected
                country = choice.split(" / ")[0]
                country_prefix = f"{country} / "
                all_country_items = [
                    i
                    for i, c in enumerate(self.choices)
                    if c.startswith(country_prefix) and c != choice
                ]
                if all_country_items:
                    return all(self.selected.get(i, False) for i in all_country_items)

        return self.selected.get(idx, False)

    def draw(self) -> None:
        self.stdscr.clear()
        max_y, max_x = self.stdscr.getmaxyx()

        # Draw title with color if enabled
        if self.colors_enabled and curses.has_colors():
            self.stdscr.addstr(0, 0, self.title[: max_x - 1], curses.color_pair(1) | curses.A_BOLD)
        else:
            self.stdscr.addstr(0, 0, self.title[: max_x - 1])

        if self.allow_back:
            help_line = (
                "SPACE select, ENTER confirm, j/k or arrows to move, b to go back, q to quit"
            )
        else:
            help_line = "SPACE select, ENTER confirm, j/k or arrows to move, q to quit"
        self.stdscr.addstr(1, 0, help_line[: max_x - 1])
        start_row = 2
        # Reserve one line at bottom for scroll indicator
        visible = max(1, max_y - start_row - 1)
        total = len(self.choices)
        # Clamp top within valid bounds
        self.top = max(0, min(self.top, max(0, total - visible)))
        end = min(total, self.top + visible)
        for i, text in enumerate(self.choices[self.top : end]):
            idx = self.top + i
            is_selected = self._get_display_selected(idx)
            prefix = "[*] " if is_selected else "[ ] " if self.multi else "    "
            line = ("> " if idx == self.current else "  ") + prefix + text
            row = start_row + i
            if row < max_y - 1:
                # Apply colors based on item state
                attr = 0
                if self.colors_enabled and curses.has_colors():
                    if idx == self.current:
                        attr = curses.color_pair(3) | curses.A_BOLD  # Yellow for current cursor
                    elif is_selected:
                        attr = curses.color_pair(2)  # Green for selected items
                self.stdscr.addstr(row, 0, line[: max_x - 1], attr)
        # scroll indicators
        if self.top > 0 and start_row < max_y - 1:
            _curses_safe_addstr(self.stdscr, start_row, max_x - 2, "^")
        if end < total and max_y - 1 >= start_row:
            _curses_safe_addstr(self.stdscr, max_y - 1, max_x - 2, "v")
        self.stdscr.refresh()

    def run(self) -> Optional[List[int]]:
        while True:
            self.draw()
            ch = self.stdscr.getch()
            if ch in (curses.KEY_DOWN, ord("j")):
                if self.current < len(self.choices) - 1:
                    self.current += 1
                # adjust scroll to keep cursor within half-page window
                max_y, _ = self.stdscr.getmaxyx()
                visible = max(1, max_y - 3)  # minus header and indicator
                half = max(1, visible // 2)
                total = len(self.choices)
                desired_top = min(max(0, self.current - half), max(0, total - visible))
                self.top = desired_top
            elif ch in (curses.KEY_UP, ord("k")):
                if self.current > 0:
                    self.current -= 1
                max_y, _ = self.stdscr.getmaxyx()
                visible = max(1, max_y - 3)
                half = max(1, visible // 2)
                total = len(self.choices)
                desired_top = min(max(0, self.current - half), max(0, total - visible))
                self.top = desired_top
            elif ch in (curses.KEY_NPAGE,):  # Page Down
                max_y, _ = self.stdscr.getmaxyx()
                visible = max(1, max_y - 3)
                self.current = min(len(self.choices) - 1, self.current + visible)
                total = len(self.choices)
                half = max(1, visible // 2)
                self.top = min(max(0, self.current - half), max(0, total - visible))
            elif ch in (curses.KEY_PPAGE,):  # Page Up
                max_y, _ = self.stdscr.getmaxyx()
                visible = max(1, max_y - 3)
                self.current = max(0, self.current - visible)
                total = len(self.choices)
                half = max(1, visible // 2)
                self.top = min(max(0, self.current - half), max(0, total - visible))
            elif ch == ord(" ") and self.multi:
                if self.all_toggle and self.current == 0 and len(self.choices) > 1:
                    # toggle all (global)
                    all_selected = all(
                        self.selected.get(i, False) for i in range(1, len(self.choices))
                    )
                    for i in range(1, len(self.choices)):
                        self.selected[i] = not all_selected
                elif self.hierarchical_all and self.current > 0:  # Skip global "[All ...]" item
                    choice = self.choices[self.current]
                    if " / All of " in choice:
                        # This is an "All of Country" item - toggle all regions for this country
                        country = choice.split(" / ")[0]
                        country_prefix = f"{country} / "
                        all_country_items = [
                            i
                            for i, c in enumerate(self.choices)
                            if c.startswith(country_prefix) and c != choice
                        ]
                        # Check if all are currently selected
                        all_selected = all(self.selected.get(i, False) for i in all_country_items)
                        # Toggle them
                        for i in all_country_items:
                            self.selected[i] = not all_selected
                    else:
                        # Regular item - toggle it and check if it affects "All of Country"
                        self.selected[self.current] = not self.selected.get(self.current, False)

                        # Check if this affects any "All of Country" items
                        if " / " in choice:
                            country = choice.split(" / ")[0]
                            country_all_item = f"{country} / All of {country}"
                            try:
                                self.choices.index(country_all_item)
                                # If all individual items are selected, the "All of Country" should be selected
                                # But we don't store this in selected dict - it's computed in _get_display_selected
                            except ValueError:
                                pass  # "All of Country" item not found, skip
                else:
                    self.selected[self.current] = not self.selected.get(self.current, False)
            elif ch in (curses.KEY_ENTER, 10, 13):
                if self.multi:
                    if not self.selected:
                        self.selected[self.current] = True
                    return [i for i, v in self.selected.items() if v]
                else:
                    return [self.current]
            elif ch == ord("b") and self.allow_back:
                return [-1]  # Special value indicating "go back"
            elif ch in (ord("q"), 27):
                return None


class ProgressScreen:
    def __init__(self, stdscr: Any, total: int, outdir: Path, colors_enabled: bool = True):
        self.stdscr = stdscr
        self.total = total
        self.completed = 0
        self.failed = 0
        self.skipped = 0
        self.status = "Running"
        self.start_time = time.time()
        self.bytes_downloaded = 0
        self.outdir = outdir
        self.avg_tile_size_bytes = 0.0
        self.current_area: str = ""
        self.colors_enabled = colors_enabled

    def on_progress(self, status: str, req: TileRequest, bytes_len: int) -> None:
        if status == "success":
            self.completed += 1
            self.bytes_downloaded += bytes_len
        elif status == "failed":
            self.failed += 1
        elif status == "skipped":
            self.skipped += 1
        self.avg_tile_size_bytes = self.bytes_downloaded / max(1, self.completed)
        try:
            if getattr(req, "area_label", None):
                self.current_area = str(req.area_label)
        except Exception:
            pass
        self.draw()

    def draw(self) -> None:
        self.stdscr.clear()
        _, max_x = self.stdscr.getmaxyx()

        # Title with color
        if self.colors_enabled and curses.has_colors():
            self.stdscr.addstr(
                0,
                0,
                "Downloading tiles  [q: cancel] [p: pause/resume]",
                curses.color_pair(1) | curses.A_BOLD,
            )
        else:
            self.stdscr.addstr(0, 0, "Downloading tiles  [q: cancel] [p: pause/resume]")

        bar_width = max_x - 2
        done_ratio = (self.completed + self.failed + self.skipped) / max(1, self.total)
        done = int(done_ratio * bar_width)
        bar = "#" * done + "-" * (bar_width - done)
        self.stdscr.addstr(2, 0, f"[{bar[:bar_width]}]")
        processed = self.completed + self.failed + self.skipped
        elapsed = max(0.001, time.time() - self.start_time)
        rate = processed / elapsed
        remain = max(0, self.total - processed)
        eta_sec = int(remain / rate) if rate > 0 else 0
        eta_min, eta_s = divmod(eta_sec, 60)

        # Status line with colored numbers
        if self.colors_enabled and curses.has_colors():
            # Build the status line with colors
            completed_str = f"{self.completed}"
            failed_str = f"{self.failed}"
            skipped_str = f"{self.skipped}"
            total_str = f"{self.total}"

            self.stdscr.addstr(3, 0, "Completed: ", curses.color_pair(7))
            self.stdscr.addstr(3, 11, completed_str, curses.color_pair(2))
            pos = 11 + len(completed_str)

            self.stdscr.addstr(3, pos, "  Failed: ", curses.color_pair(7))
            self.stdscr.addstr(3, pos + 11, failed_str, curses.color_pair(4))
            pos += 11 + len(failed_str)

            self.stdscr.addstr(3, pos, "  Skipped: ", curses.color_pair(7))
            self.stdscr.addstr(3, pos + 12, skipped_str, curses.color_pair(3))
            pos += 12 + len(skipped_str)

            self.stdscr.addstr(3, pos, "  Total: ", curses.color_pair(7))
            self.stdscr.addstr(3, pos + 9, total_str, curses.color_pair(3) | curses.A_BOLD)
        else:
            self.stdscr.addstr(
                3,
                0,
                f"Completed: {self.completed}  Failed: {self.failed}  Skipped: {self.skipped}  Total: {self.total}",
            )

        # Rate and ETA with colors
        if self.colors_enabled and curses.has_colors():
            rate_str = f"{rate:.1f} tiles/s"
            eta_str = f"{eta_min}m {eta_s}s"

            self.stdscr.addstr(4, 0, "Rate: ", curses.color_pair(7) | curses.A_BOLD)
            self.stdscr.addstr(4, 6, rate_str, curses.color_pair(3) | curses.A_BOLD)
            self.stdscr.addstr(
                4, 6 + len(rate_str), "   ETA: ", curses.color_pair(7) | curses.A_BOLD
            )
            self.stdscr.addstr(
                4, 6 + len(rate_str) + 8, eta_str, curses.color_pair(5) | curses.A_BOLD
            )
        else:
            self.stdscr.addstr(4, 0, f"Rate: {rate:.1f} tiles/s   ETA: {eta_min}m {eta_s}s")

        # Disk stats with colors
        if self.colors_enabled and curses.has_colors():
            downloaded_str = human_bytes(self.bytes_downloaded)
            self.stdscr.addstr(5, 0, "Downloaded: ", curses.color_pair(6) | curses.A_BOLD)
            self.stdscr.addstr(5, 12, downloaded_str, curses.color_pair(2) | curses.A_BOLD)
        else:
            self.stdscr.addstr(5, 0, f"Downloaded: {human_bytes(self.bytes_downloaded)}")

        est_total_bytes = (
            int(self.avg_tile_size_bytes * self.total) if self.avg_tile_size_bytes > 0 else 0
        )
        if self.colors_enabled and curses.has_colors():
            est_size_str = human_bytes(est_total_bytes)
            outdir_str = str(self.outdir)

            self.stdscr.addstr(6, 0, "Estimated final size: ", curses.color_pair(7))
            self.stdscr.addstr(6, 22, est_size_str, curses.color_pair(3))
            pos = 22 + len(est_size_str)
            self.stdscr.addstr(6, pos, "  Out: ", curses.color_pair(1))
            self.stdscr.addstr(6, pos + 7, outdir_str, curses.color_pair(6))
        else:
            self.stdscr.addstr(
                6,
                0,
                f"Estimated final size: {human_bytes(est_total_bytes)}  Out: {str(self.outdir)}",
            )

        # Status with color based on status
        if self.colors_enabled and curses.has_colors():
            # Status label in bright white
            self.stdscr.addstr(8, 0, "Status: ", curses.color_pair(8) | curses.A_BOLD)

            # Status value with appropriate color
            status_attr = 0
            if "Running" in self.status:
                status_attr = curses.color_pair(9) | curses.A_BOLD  # Bright green for running
            elif "Completed" in self.status:
                status_attr = curses.color_pair(2)  # Green for completed
            elif "Cancelled" in self.status or "Failed" in self.status:
                status_attr = curses.color_pair(4)  # Red for cancelled/failed
            elif "Paused" in self.status:
                status_attr = curses.color_pair(3)  # Yellow for paused
            else:
                status_attr = curses.color_pair(5)  # Blue for other statuses

            self.stdscr.addstr(8, 8, self.status, status_attr)
        else:
            self.stdscr.addstr(8, 0, f"Status: {self.status}")

        if self.current_area:
            if self.colors_enabled and curses.has_colors():
                self.stdscr.addstr(9, 0, f"Area: {self.current_area}", curses.color_pair(6))
            else:
                self.stdscr.addstr(9, 0, f"Area: {self.current_area}")

        self.stdscr.refresh()


def _build_requests(
    regions: Dict[str, Tuple[float, float, float, float]], min_zoom: int, max_zoom: int
) -> List[TileRequest]:
    reqs: List[TileRequest] = []
    for z in range(min_zoom, max_zoom + 1):
        for south, west, north, east in regions.values():
            for zz, x, y in iter_tiles_for_bbox(south, west, north, east, z):
                reqs.append(TileRequest(zz, x, y))
    return reqs


def tui_main(stdscr: Any, colors_enabled: bool = True) -> int:
    curses.curs_set(0)

    # Initialize colors if enabled and supported
    if colors_enabled and curses.has_colors():
        curses.start_color()
        curses.use_default_colors()

        # Define color pairs that work well on both light and dark terminal backgrounds
        # Using colors that provide good contrast regardless of background
        curses.init_pair(1, curses.COLOR_CYAN, -1)  # Title/header color (cyan works on both)
        curses.init_pair(2, curses.COLOR_GREEN, -1)  # Selected item color (green works on both)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Current cursor color (yellow works on both)
        curses.init_pair(4, curses.COLOR_RED, -1)  # Error/warning color (red works on both)
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)  # Progress/info color (magenta works on both)
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)  # Status color (magenta works on both)
        curses.init_pair(
            7, curses.COLOR_CYAN, -1
        )  # Captions (cyan for better visibility than white)
        curses.init_pair(8, curses.COLOR_CYAN, -1)  # Status label (cyan for consistency)
        curses.init_pair(9, curses.COLOR_GREEN, -1)  # Bright green (for Running status)

    catalog = load_region_catalog()

    # Continents selection loop
    while True:
        continents = list(catalog.keys())
        cont_choices = ["[All continents]"] + continents
        sel = Menu(
            stdscr,
            "Select continents (SPACE to multi-select)",
            cont_choices,
            multi=True,
            all_toggle=True,
            colors_enabled=colors_enabled,
        ).run()
        if not sel:
            return 1
        if 0 in sel:
            selected_continents = continents
        else:
            selected_continents = [continents[i - 1] for i in sel]

        # Countries selection loop
        while True:
            country_items: List[Tuple[str, Tuple[str, str]]] = []  # (label, (continent, country))
            for cont in selected_continents:
                for country in catalog[cont].keys():
                    country_items.append((f"{cont} / {country}", (cont, country)))
            if not country_items:
                return 1
            country_labels = ["[All countries]"] + [lbl for lbl, _ in country_items]
            sel = Menu(
                stdscr,
                "Select countries (SPACE to multi-select)",
                country_labels,
                multi=True,
                all_toggle=True,
                colors_enabled=colors_enabled,
                allow_back=True,
            ).run()
            if sel == [-1]:  # Back to continents
                break
            if not sel:
                return 1
            if 0 in sel:
                selected_pairs = [pair for _, pair in country_items]
            else:
                selected_pairs = [country_items[i - 1][1] for i in sel]

            # States selection loop
            while True:
                state_items: List[Tuple[str, Tuple[str, str, str]]] = (
                    []
                )  # (label, (continent, country, state))
                for cont, country in selected_pairs:
                    for state in catalog[cont][country].keys():
                        state_items.append((f"{country} / {state}", (cont, country, state)))
                if not state_items:
                    return 1
                state_labels = ["[All states/regions]"] + [lbl for lbl, _ in state_items]
                sel = Menu(
                    stdscr,
                    "Select states/regions (SPACE to multi-select)",
                    state_labels,
                    multi=True,
                    all_toggle=True,
                    hierarchical_all=True,
                    colors_enabled=colors_enabled,
                    allow_back=True,
                ).run()
                if sel == [-1]:  # Back to countries
                    break
                if not sel:
                    return 1
                if 0 in sel:
                    chosen_states = [meta for _, meta in state_items]
                else:
                    chosen_states = [state_items[i - 1][1] for i in sel]
                regions = {
                    f"{country} — {state}": catalog[cont][country][state]
                    for (cont, country, state) in chosen_states
                }

                # Provider selection loop
                while True:
                    providers = list(PROVIDERS.keys())
                    sel = Menu(
                        stdscr,
                        "Select map provider",
                        providers,
                        multi=False,
                        colors_enabled=colors_enabled,
                        allow_back=True,
                    ).run()
                    if sel == [-1]:  # Back to states
                        break
                    if not sel:
                        return 1
                    provider_key = providers[sel[0]]
                    provider = PROVIDERS[provider_key]
                    style = provider.default_style

                    # Style selection loop (only if provider has styles)
                    if provider.styles:
                        while True:
                            styles = provider.styles
                            sel = Menu(
                                stdscr,
                                "Select provider style",
                                styles,
                                multi=False,
                                colors_enabled=colors_enabled,
                                allow_back=True,
                            ).run()
                            if sel == [-1]:  # Back to provider
                                break
                            if not sel:
                                return 1
                            style = styles[sel[0]]
                            # If we reach here, we've completed all selections
                            break
                        if sel == [-1]:
                            continue  # Back to provider selection
                    # If we reach here, we've completed all selections
                    break
                if sel == [-1]:
                    continue  # Back to states selection
                # If we reach here, we've completed all selections
                break
            if sel == [-1]:
                continue  # Back to countries selection
            # If we reach here, we've completed all selections
            break
        if sel == [-1]:
            continue  # Back to continents selection
        # If we reach here, we've completed all selections
        break
    # API key screen if needed
    api_key: Optional[str] = None
    if provider.requires_api_key:
        # fall back to env
        env_key = provider.api_key_env or ""
        api_key = os.getenv(env_key)
        if not api_key:
            curses.echo()
            stdscr.clear()
            if colors_enabled and curses.has_colors():
                stdscr.addstr(
                    0,
                    0,
                    f"Enter API key for {provider.display_name}:",
                    curses.color_pair(1) | curses.A_BOLD,
                )
            else:
                stdscr.addstr(0, 0, f"Enter API key for {provider.display_name}:")
            stdscr.refresh()
            api_key = _safe_getstr(stdscr, 1, 0, 256)
            curses.noecho()
    # Zoom levels and outdir
    curses.echo()
    stdscr.clear()
    if colors_enabled and curses.has_colors():
        stdscr.addstr(0, 0, "Max zoom (default 12):", curses.color_pair(1) | curses.A_BOLD)
        max_zoom_s = _safe_getstr(stdscr, 0, 23, 4, default="12")
        stdscr.addstr(
            1, 0, "Output directory (default ~/tiles):", curses.color_pair(1) | curses.A_BOLD
        )
        outdir_s = _safe_getstr(stdscr, 1, 34, 256, default=os.path.expanduser("~/tiles"))
        stdscr.addstr(
            2,
            0,
            f"Concurrency (default {provider.default_concurrency}):",
            curses.color_pair(1) | curses.A_BOLD,
        )
    else:
        stdscr.addstr(0, 0, "Max zoom (default 12):")
        max_zoom_s = _safe_getstr(stdscr, 0, 23, 4, default="12")
        stdscr.addstr(1, 0, "Output directory (default ~/tiles):")
        outdir_s = _safe_getstr(stdscr, 1, 34, 256, default=os.path.expanduser("~/tiles"))
        stdscr.addstr(2, 0, f"Concurrency (default {provider.default_concurrency}):")
    conc_s = _safe_getstr(
        stdscr,
        2,
        36 + len(str(provider.default_concurrency)),
        4,
        default=str(provider.default_concurrency),
    )
    curses.noecho()
    min_zoom = 1
    max_zoom = int(max_zoom_s)
    outdir = Path(outdir_s)
    concurrency = int(conc_s)
    total = count_tiles_for_regions(regions, min_zoom, max_zoom)
    # Estimate average tile size via sampling
    url_builder = get_url_builder(provider, api_key=api_key, style=style)
    est_avg = _estimate_avg_tile_size_sync(
        url_builder, provider.headers, regions, min_zoom, max_zoom
    )
    # Show pre-start estimation
    stdscr.clear()
    if colors_enabled and curses.has_colors():
        stdscr.addstr(0, 0, f"Planned tiles: {total}", curses.color_pair(5) | curses.A_BOLD)
        stdscr.addstr(
            1, 0, f"Estimated average tile size: {human_bytes(int(est_avg))}", curses.color_pair(5)
        )
        stdscr.addstr(
            2, 0, f"Estimated final size: {human_bytes(int(est_avg * total))}", curses.color_pair(5)
        )
        stdscr.addstr(
            4, 0, "Press ENTER to start, q to cancel", curses.color_pair(2) | curses.A_BOLD
        )
    else:
        stdscr.addstr(0, 0, f"Planned tiles: {total}")
        stdscr.addstr(1, 0, f"Estimated average tile size: {human_bytes(int(est_avg))}")
        stdscr.addstr(2, 0, f"Estimated final size: {human_bytes(int(est_avg * total))}")
        stdscr.addstr(4, 0, "Press ENTER to start, q to cancel")
    stdscr.refresh()
    while True:
        ch = stdscr.getch()
        if ch in (curses.KEY_ENTER, 10, 13):
            break
        if ch in (ord("q"), 27):
            return 0
    prog = ProgressScreen(stdscr, total=total, outdir=outdir, colors_enabled=colors_enabled)
    prog.avg_tile_size_bytes = est_avg
    prog.draw()
    # Build downloader and tasks
    downloader = TileDownloader(
        outdir, url_builder, headers=provider.headers, concurrent_requests=concurrency
    )
    requests = _build_requests(regions, min_zoom, max_zoom)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(downloader.download(requests, on_progress=prog.on_progress))
    stdscr.nodelay(True)
    try:
        while not task.done():
            try:
                ch = stdscr.getch()
                if ch == ord("q"):
                    downloader.cancel()
                    prog.status = "Cancelling..."
                    prog.draw()
                elif ch == ord("p"):
                    if downloader.paused:
                        downloader.resume()
                        prog.status = "Running"
                    else:
                        downloader.pause()
                        prog.status = "Paused"
                    prog.draw()
                loop.run_until_complete(asyncio.sleep(0.05))
            except KeyboardInterrupt:
                downloader.cancel()
                prog.status = "Cancelling (Ctrl+C)..."
                prog.draw()
                break
        # Gracefully finish/cancel background task
        try:
            loop.run_until_complete(asyncio.wait_for(task, timeout=5))
        except Exception:
            try:
                task.cancel()
                loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
            except Exception:
                pass
        loop.run_until_complete(asyncio.sleep(0))
    finally:
        try:
            loop.run_until_complete(asyncio.sleep(0))
        except Exception:
            pass
        loop.close()
    prog.status = "Completed" if not downloader.cancelled else "Cancelled"
    prog.draw()
    stdscr.nodelay(False)
    if colors_enabled and curses.has_colors():
        stdscr.addstr(7, 0, "Press any key to exit...", curses.color_pair(2) | curses.A_BOLD)
    else:
        stdscr.addstr(7, 0, "Press any key to exit...")
    stdscr.getch()
    return 0


def main_tui(colors_enabled: bool = True) -> int:
    """Entry-point for the interactive *text* UI.

    If a working :pymod:`curses` implementation is available, the full-featured
    curses TUI is launched.  Otherwise (e.g. on vanilla Windows where curses is
    missing) we silently fall back to the *wizard* flow that uses
    :pypi:`questionary` for an interactive - but non-curses - experience.  This
    guarantees that invoking the application without any parameters always
    opens a user-friendly text interface, regardless of the underlying
    platform.
    """

    if not HAS_CURSES:
        # Defer import to avoid a hard dependency on questionary when curses is
        # available.
        from .cli import _run_wizard

        # Run the wizard in normal (non-dry-run) mode.
        return _run_wizard(dry_run=False)

    return curses.wrapper(tui_main, colors_enabled)


def _safe_getstr(stdscr: Any, y: int, x: int, n: int, default: Optional[str] = None) -> str:
    bs: bytes = stdscr.getstr(y, x, n)
    try:
        s = bs.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        enc = locale.getpreferredencoding(False) or "utf-8"
        s = bs.decode(enc, errors="replace")
    s = s.strip()
    if not s and default is not None:
        return default
    return s


def _curses_safe_addstr(stdscr: Any, y: int, x: int, text: str) -> None:
    try:
        max_y, max_x = stdscr.getmaxyx()
        if y < 0 or y >= max_y:
            return
        if x < 0 or x >= max_x:
            return
        # avoid bottom-right cell by reserving one column
        max_len = max_x - x - 1
        if max_len <= 0:
            return
        stdscr.addstr(y, x, text[:max_len])
    except Exception:
        # Best-effort draw; ignore rendering errors in tiny terminals
        pass


def human_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.1f} {u}"
        size /= 1024
    # Fallback (should not be reached)
    return f"{size:.1f} {units[-1]}"


def _estimate_avg_tile_size_sync(
    url_builder: Any,
    headers: Dict[str, str],
    regions: Dict[str, Tuple[float, float, float, float]],
    min_zoom: int,
    max_zoom: int,
) -> float:
    # Pick up to 10 sample tiles across regions and zooms
    samples: List[Tuple[int, int, int]] = []
    zooms = list(range(min_zoom, max_zoom + 1))
    random.shuffle(zooms)
    for z in zooms:
        for south, west, north, east in regions.values():
            sx, ex = lon2tilex(west, z), lon2tilex(east, z)
            sy, ey = lat2tiley(north, z), lat2tiley(south, z)
            if sx > ex or sy > ey:
                continue
            x = random.randint(sx, ex)
            y = random.randint(sy, ey)
            samples.append((z, x, y))
            if len(samples) >= 10:
                break
        if len(samples) >= 10:
            break

    async def _fetch_head(session: aiohttp.ClientSession, z: int, x: int, y: int) -> int:
        url = url_builder(z, x, y)
        try:
            async with session.head(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                cl = r.headers.get("Content-Length")
                if cl:
                    return int(cl)
        except Exception:
            pass
        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                if r.status == 200:
                    data = await r.read()
                    return len(data)
        except Exception:
            pass
        return 0

    async def _estimate() -> float:
        if not samples:
            return 0.0
        async with aiohttp.ClientSession() as session:
            sizes = await asyncio.gather(*[_fetch_head(session, z, x, y) for (z, x, y) in samples])
        vals = [s for s in sizes if s > 0]
        if not vals:
            return 0.0
        return sum(vals) / len(vals)

    try:
        return asyncio.run(_estimate())
    except RuntimeError:
        # already inside loop; create a new loop temporarily
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_estimate())
        finally:
            loop.close()
