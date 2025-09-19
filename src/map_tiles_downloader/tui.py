from __future__ import annotations

import asyncio
import curses
import os
import time
import locale
import random
from typing import Iterable, Optional, Tuple, Dict, List
import aiohttp
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .providers import PROVIDERS, get_url_builder
from .regions import load_region_catalog
from .tiling import count_tiles_for_regions, lon2tilex, lat2tiley
from .downloader import TileDownloader, TileRequest
from .tiling import iter_tiles_for_bbox


class Menu:
    def __init__(self, stdscr, title: str, choices: List[str], multi: bool = False, all_toggle: bool = False):
        self.stdscr = stdscr
        self.title = title
        self.choices = choices
        self.multi = multi
        self.all_toggle = all_toggle
        self.current = 0
        self.selected: Dict[int, bool] = {}
        self.top = 0  # index of first visible item for scrolling

    def draw(self):
        self.stdscr.clear()
        max_y, max_x = self.stdscr.getmaxyx()
        self.stdscr.addstr(0, 0, self.title[: max_x - 1])
        help_line = "SPACE select, ENTER confirm, j/k or arrows to move, q to quit"
        self.stdscr.addstr(1, 0, help_line[: max_x - 1])
        start_row = 2
        # Reserve one line at bottom for scroll indicator
        visible = max(1, max_y - start_row - 1)
        total = len(self.choices)
        # Clamp top within valid bounds
        self.top = max(0, min(self.top, max(0, total - visible)))
        end = min(total, self.top + visible)
        for i, text in enumerate(self.choices[self.top:end]):
            idx = self.top + i
            is_selected = self.selected.get(idx, False)
            if self.all_toggle and self.multi and idx == 0:
                # reflect selected if all others are selected
                if all(self.selected.get(i, False) for i in range(1, len(self.choices)) if len(self.choices) > 1):
                    is_selected = True
            prefix = "[*] " if is_selected else "[ ] " if self.multi else "    "
            line = ("> " if idx == self.current else "  ") + prefix + text
            row = start_row + i
            if row < max_y - 1:
                self.stdscr.addstr(row, 0, line[: max_x - 1])
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
                    # toggle all
                    all_selected = all(self.selected.get(i, False) for i in range(1, len(self.choices)))
                    for i in range(1, len(self.choices)):
                        self.selected[i] = not all_selected
                else:
                    self.selected[self.current] = not self.selected.get(self.current, False)
            elif ch in (curses.KEY_ENTER, 10, 13):
                if self.multi:
                    if not self.selected:
                        self.selected[self.current] = True
                    return [i for i, v in self.selected.items() if v]
                else:
                    return [self.current]
            elif ch in (ord("q"), 27):
                return None


class ProgressScreen:
    def __init__(self, stdscr, total: int, outdir: Path):
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

    def on_progress(self, status: str, req, bytes_len: int):
        if status == "success":
            self.completed += 1
            self.bytes_downloaded += bytes_len
        elif status == "failed":
            self.failed += 1
        elif status == "skipped":
            self.skipped += 1
        processed = max(1, self.completed + self.failed + self.skipped)
        self.avg_tile_size_bytes = self.bytes_downloaded / max(1, self.completed)
        try:
            if getattr(req, 'area_label', None):
                self.current_area = str(req.area_label)
        except Exception:
            pass
        self.draw()

    def draw(self):
        self.stdscr.clear()
        _, max_x = self.stdscr.getmaxyx()
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
        self.stdscr.addstr(3, 0, f"Completed: {self.completed}  Failed: {self.failed}  Skipped: {self.skipped}  Total: {self.total}")
        self.stdscr.addstr(4, 0, f"Rate: {rate:.1f} tiles/s   ETA: {eta_min}m {eta_s}s")
        # Disk stats
        self.stdscr.addstr(5, 0, f"Downloaded: {human_bytes(self.bytes_downloaded)}")
        remaining_tiles = max(0, self.total - processed)
        est_total_bytes = int(self.avg_tile_size_bytes * self.total) if self.avg_tile_size_bytes > 0 else 0
        self.stdscr.addstr(6, 0, f"Estimated final size: {human_bytes(est_total_bytes)}  Out: {str(self.outdir)}")
        self.stdscr.addstr(8, 0, f"Status: {self.status}")
        if self.current_area:
            self.stdscr.addstr(9, 0, f"Area: {self.current_area}")
        self.stdscr.refresh()


def _build_requests(regions: Dict[str, Tuple[float, float, float, float]], min_zoom: int, max_zoom: int) -> List[TileRequest]:
    reqs: List[TileRequest] = []
    for z in range(min_zoom, max_zoom + 1):
        for (south, west, north, east) in regions.values():
            for zz, x, y in iter_tiles_for_bbox(south, west, north, east, z):
                reqs.append(TileRequest(zz, x, y))
    return reqs


def tui_main(stdscr) -> int:
    curses.curs_set(0)
    catalog = load_region_catalog()

    # Continents (multi-select)
    continents = list(catalog.keys())
    cont_choices = ["[All continents]"] + continents
    sel = Menu(stdscr, "Select continents (SPACE to multi-select)", cont_choices, multi=True, all_toggle=True).run()
    if not sel:
        return 1
    if 0 in sel:
        selected_continents = continents
    else:
        selected_continents = [continents[i - 1] for i in sel]

    # Countries (multi-select across selected continents)
    country_items: List[Tuple[str, Tuple[str, str]]] = []  # (label, (continent, country))
    for cont in selected_continents:
        for country in catalog[cont].keys():
            country_items.append((f"{cont} / {country}", (cont, country)))
    if not country_items:
        return 1
    country_labels = ["[All countries]"] + [lbl for lbl, _ in country_items]
    sel = Menu(stdscr, "Select countries (SPACE to multi-select)", country_labels, multi=True, all_toggle=True).run()
    if not sel:
        return 1
    if 0 in sel:
        selected_pairs = [pair for _, pair in country_items]
    else:
        selected_pairs = [country_items[i - 1][1] for i in sel]

    # States (multi-select across selected countries)
    state_items: List[Tuple[str, Tuple[str, str, str]]] = []  # (label, (continent, country, state))
    for cont, country in selected_pairs:
        for state in catalog[cont][country].keys():
            state_items.append((f"{country} / {state}", (cont, country, state)))
    if not state_items:
        return 1
    state_labels = ["[All states/regions]"] + [lbl for lbl, _ in state_items]
    sel = Menu(stdscr, "Select states/regions (SPACE to multi-select)", state_labels, multi=True, all_toggle=True).run()
    if not sel:
        return 1
    if 0 in sel:
        chosen_states = [meta for _, meta in state_items]
    else:
        chosen_states = [state_items[i - 1][1] for i in sel]
    regions = {f"{country} — {state}": catalog[cont][country][state] for (cont, country, state) in chosen_states}

    providers = list(PROVIDERS.keys())
    sel = Menu(stdscr, "Select map provider", providers, multi=False).run()
    if not sel:
        return 1
    provider_key = providers[sel[0]]
    provider = PROVIDERS[provider_key]

    style = provider.default_style
    if provider.styles:
        styles = provider.styles
        sel = Menu(stdscr, "Select provider style", styles, multi=False).run()
        if not sel:
            return 1
        style = styles[sel[0]]

    # API key screen if needed
    api_key = None
    if provider.requires_api_key:
        # fall back to env
        env_key = provider.api_key_env or ""
        api_key = os.getenv(env_key)
        if not api_key:
            curses.echo()
            stdscr.clear()
            stdscr.addstr(0, 0, f"Enter API key for {provider.display_name}:")
            stdscr.refresh()
            api_key = _safe_getstr(stdscr, 1, 0, 256)
            curses.noecho()

    # Zoom levels and outdir
    curses.echo()
    stdscr.clear()
    stdscr.addstr(0, 0, "Min zoom (default 3):")
    min_zoom_s = _safe_getstr(stdscr, 0, 22, 4, default="3")
    stdscr.addstr(1, 0, "Max zoom (default 12):")
    max_zoom_s = _safe_getstr(stdscr, 1, 23, 4, default="12")
    stdscr.addstr(2, 0, "Output directory (default ~/maps):")
    outdir_s = _safe_getstr(stdscr, 2, 34, 256, default=os.path.expanduser("~/maps"))
    stdscr.addstr(3, 0, f"Concurrency (default {provider.default_concurrency}):")
    conc_s = _safe_getstr(stdscr, 3, 36 + len(str(provider.default_concurrency)), 4, default=str(provider.default_concurrency))
    curses.noecho()

    min_zoom = int(min_zoom_s)
    max_zoom = int(max_zoom_s)
    outdir = Path(outdir_s)
    concurrency = int(conc_s)

    total = count_tiles_for_regions(regions, min_zoom, max_zoom)

    # Estimate average tile size via sampling
    url_builder = get_url_builder(provider, api_key=api_key, style=style)
    est_avg = _estimate_avg_tile_size_sync(url_builder, provider.headers, regions, min_zoom, max_zoom)

    # Show pre-start estimation
    stdscr.clear()
    stdscr.addstr(0, 0, f"Planned tiles: {total}")
    stdscr.addstr(1, 0, f"Estimated average tile size: {human_bytes(int(est_avg))}")
    stdscr.addstr(2, 0, f"Estimated final size: {human_bytes(int(est_avg * total))}")
    stdscr.addstr(4, 0, "Press ENTER to start, q to cancel")
    stdscr.refresh()
    while True:
        ch = stdscr.getch()
        if ch in (curses.KEY_ENTER, 10, 13):
            break
        if ch in (ord('q'), 27):
            return 0

    prog = ProgressScreen(stdscr, total=total, outdir=outdir)
    prog.avg_tile_size_bytes = est_avg
    prog.draw()

    # Build downloader and tasks
    downloader = TileDownloader(outdir, url_builder, headers=provider.headers, concurrent_requests=concurrency)
    requests = _build_requests(regions, min_zoom, max_zoom)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    task = loop.create_task(downloader.download(requests, on_progress=prog.on_progress))

    stdscr.nodelay(True)
    cancelled_by_user = False
    try:
        while not task.done():
            try:
                ch = stdscr.getch()
                if ch == ord('q'):
                    cancelled_by_user = True
                    downloader.cancel()
                    prog.status = "Cancelling..."
                    prog.draw()
                elif ch == ord('p'):
                    if downloader.paused:
                        downloader.resume()
                        prog.status = "Running"
                    else:
                        downloader.pause()
                        prog.status = "Paused"
                    prog.draw()
                loop.run_until_complete(asyncio.sleep(0.05))
            except KeyboardInterrupt:
                cancelled_by_user = True
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
    stdscr.addstr(7, 0, "Press any key to exit...")
    stdscr.getch()
    return 0


def main_tui() -> int:
    return curses.wrapper(tui_main)


def _safe_getstr(stdscr, y: int, x: int, n: int, default: Optional[str] = None) -> str:
    bs = stdscr.getstr(y, x, n)
    try:
        s = bs.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        enc = locale.getpreferredencoding(False) or "utf-8"
        s = bs.decode(enc, errors="replace")
    s = s.strip()
    if not s and default is not None:
        return default
    return s


def _curses_safe_addstr(stdscr, y: int, x: int, text: str) -> None:
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


def _estimate_avg_tile_size_sync(url_builder, headers: Dict[str, str], regions: Dict[str, Tuple[float, float, float, float]], min_zoom: int, max_zoom: int) -> float:
    # Pick up to 10 sample tiles across regions and zooms
    samples: List[Tuple[int, int, int]] = []
    zooms = list(range(min_zoom, max_zoom + 1))
    random.shuffle(zooms)
    for z in zooms:
        for (south, west, north, east) in regions.values():
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
            async with session.head(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
                cl = r.headers.get("Content-Length")
                if cl:
                    return int(cl)
        except Exception:
            pass
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
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


