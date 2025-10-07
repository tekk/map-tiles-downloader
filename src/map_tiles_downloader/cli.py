from __future__ import annotations

import argparse
import asyncio
import logging
import os
import platform
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .downloader import TileDownloader, TileRequest
from .tiling import iter_tiles_for_bbox, count_tiles_for_regions
from .kml_regions import kml_to_regions
from .providers import PROVIDERS, get_url_builder
from .regions import load_region_catalog, RegionCatalog
from .tui import main_tui
import questionary


DEFAULT_OUTDIR = Path(os.path.expanduser("~/tiles"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="map-tiles-downloader",
        description="Download Thunderforest map tiles by bounding box or from KML waypoints/routes.",
    )

    sub = parser.add_subparsers(dest="command", required=False)

    if platform.system() == "Windows":
        p_wizard = sub.add_parser("wizard", help="Interactive selection of region and provider.")
        p_wizard.add_argument(
            "--log-level",
            type=str,
            default="INFO",
            choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        )
        p_wizard.add_argument(
            "--dry-run", action="store_true", help="Plan only and show tile count, no download"
        )

    # Subcommand: bbox
    p_bbox = sub.add_parser("bbox", help="Download tiles for a bounding box.")
    p_bbox.add_argument("south", type=float)
    p_bbox.add_argument("west", type=float)
    p_bbox.add_argument("north", type=float)
    p_bbox.add_argument("east", type=float)
    p_bbox.add_argument("--max-zoom", type=int, default=14)
    p_bbox.add_argument(
        "--provider", type=str, default="thunderforest", choices=list(PROVIDERS.keys())
    )
    p_bbox.add_argument("--style", type=str, default=None)
    p_bbox.add_argument("--api-key", "-k", type=str, default=None)
    p_bbox.add_argument("--outdir", "-o", type=Path, default=DEFAULT_OUTDIR)
    p_bbox.add_argument("--concurrency", type=int, default=20)
    p_bbox.add_argument("--max-tiles", type=int, default=None)
    p_bbox.add_argument(
        "--dry-run", action="store_true", help="Plan only and show tile count, no download"
    )
    p_bbox.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    )

    # Subcommand: kml
    p_kml = sub.add_parser("kml", help="Download tiles derived from KML points/routes.")
    p_kml.add_argument("kmlfile", type=Path)
    p_kml.add_argument("--latrgn", type=float, default=0.1)
    p_kml.add_argument("--lonrgn", type=float, default=0.1)
    p_kml.add_argument("--max-zoom", type=int, default=14)
    p_kml.add_argument(
        "--provider", type=str, default="thunderforest", choices=list(PROVIDERS.keys())
    )
    p_kml.add_argument("--style", type=str, default=None)
    p_kml.add_argument("--api-key", "-k", type=str, default=None)
    p_kml.add_argument("--outdir", "-o", type=Path, default=DEFAULT_OUTDIR)
    p_kml.add_argument("--concurrency", type=int, default=20)
    p_kml.add_argument("--max-tiles", type=int, default=None)
    p_kml.add_argument(
        "--dry-run", action="store_true", help="Plan only and show tile count, no download"
    )
    p_kml.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    )

    # Subcommand: list providers/regions
    p_list = sub.add_parser("list", help="List providers or regions")
    p_list.add_argument("what", choices=["providers", "regions"], help="What to list")

    # Subcommand: tui (curses-based)
    p_tui = sub.add_parser("tui", help="Launch text-based installer UI")
    p_tui.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    )
    p_tui.add_argument(
        "--no-colors",
        action="store_true",
        help="Disable colored output in TUI mode",
    )

    return parser


def _requests_for_regions(
    regions: Dict[str, Tuple[float, float, float, float]],
    min_zoom: int,
    max_zoom: int,
    max_tiles: Optional[int],
) -> List[TileRequest]:
    requests: List[TileRequest] = []
    nofetch: List[Tuple[int, int, int]] = []

    for zoom in range(min_zoom, max_zoom + 1):
        for south, west, north, east in regions.values():
            for z, x, y in iter_tiles_for_bbox(south, west, north, east, zoom):
                if max_tiles is None or len(requests) < max_tiles:
                    requests.append(TileRequest(z, x, y))
                else:
                    nofetch.append((z, x, y))

    return requests


def _has_curses() -> bool:
    import importlib.util

    return importlib.util.find_spec("curses") is not None


def _run_interactive(dry_run: bool = False) -> int:
    # Always attempt the TUI first; it will fall back to the wizard internally
    # if curses is unavailable or fails to initialise.
    try:
        return main_tui()
    except Exception as exc:
        # Best-effort recovery: if curses blew up mid-initialisation (e.g. very
        # small terminal) fall back to the wizard instead of aborting.
        logging.debug("TUI failed, falling back to wizard: %s", exc)
        if dry_run:
            return _run_wizard(dry_run=True)
        return _run_wizard()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        logging.basicConfig(level=logging.INFO)
        return _run_interactive()

    if args.command == "wizard":
        logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
        return _run_interactive(dry_run=bool(args.dry_run))

    if args.command == "bbox":
        logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
        regions = {"bbox": (args.south, args.west, args.north, args.east)}
        requests = _requests_for_regions(regions, 1, args.max_zoom, args.max_tiles)
        provider = PROVIDERS[args.provider]
        api_key = args.api_key or (
            os.getenv(provider.api_key_env) if provider.api_key_env else None
        )
        if provider.requires_api_key and not api_key:
            parser.error(
                f"--api-key or {provider.api_key_env} environment variable is required for {provider.display_name}"
            )
        style = args.style or provider.default_style
        url_builder = get_url_builder(provider, api_key=api_key, style=style)
        concurrency = args.concurrency if args.concurrency else provider.default_concurrency
        if args.dry_run:
            total = count_tiles_for_regions(regions, 1, args.max_zoom)
            print(f"Planned tiles: {total}", flush=True)
        else:
            downloader = TileDownloader(
                args.outdir, url_builder, headers=provider.headers, concurrent_requests=concurrency
            )
            asyncio.run(downloader.download(requests))
        return 0

    if args.command == "kml":
        logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
        regions = kml_to_regions(args.kmlfile, latrgn=args.latrgn, lonrgn=args.lonrgn)
        requests = _requests_for_regions(regions, 1, args.max_zoom, args.max_tiles)
        provider = PROVIDERS[args.provider]
        api_key = args.api_key or (
            os.getenv(provider.api_key_env) if provider.api_key_env else None
        )
        if provider.requires_api_key and not api_key:
            parser.error(
                f"--api-key or {provider.api_key_env} environment variable is required for {provider.display_name}"
            )
        style = args.style or provider.default_style
        url_builder = get_url_builder(provider, api_key=api_key, style=style)
        concurrency = args.concurrency if args.concurrency else provider.default_concurrency
        if args.dry_run:
            total = count_tiles_for_regions(regions, 1, args.max_zoom)
            print(f"Planned tiles: {total}", flush=True)
        else:
            downloader = TileDownloader(
                args.outdir, url_builder, headers=provider.headers, concurrent_requests=concurrency
            )
            asyncio.run(downloader.download(requests))
        return 0

    if args.command == "list":
        if args.what == "providers":
            for key, p in PROVIDERS.items():
                styles = ", ".join(p.styles) if p.styles else "-"
                req = "yes" if p.requires_api_key else "no"
                print(f"{key}: styles=[{styles}] api_key_required={req}")
            return 0
        if args.what == "regions":
            catalog = load_region_catalog()
            for cont, countries in catalog.items():
                print(cont)
                for country, states in countries.items():
                    print(f"  {country}")
                    for state in states.keys():
                        print(f"    {state}")
            return 0

    if args.command == "tui":
        return main_tui(colors_enabled=not getattr(args, "no_colors", False))

    parser.print_help()
    return 1


def _run_wizard(dry_run: bool = False) -> int:
    print("Map Tiles Downloader Wizard")
    print("============================")
    catalog: RegionCatalog = load_region_catalog()

    continent = questionary.select("Select a continent:", choices=list(catalog.keys())).ask()
    country = questionary.select("Select a country:", choices=list(catalog[continent].keys())).ask()
    states = questionary.checkbox(
        "Select one or more states/regions:",
        choices=list(catalog[continent][country].keys()),
    ).ask()
    if not states:
        print("No regions selected.")
        return 1
    regions = {s: catalog[continent][country][s] for s in states}

    provider_key = questionary.select("Select a provider:", choices=list(PROVIDERS.keys())).ask()
    provider = PROVIDERS[provider_key]

    style = None
    if provider.styles:
        style = questionary.select(
            f"Select a style (default {provider.default_style}):",
            choices=provider.styles,
            default=provider.default_style or provider.styles[0],
        ).ask()

    max_zoom = int(questionary.text("Max zoom (default 12):", default="12").ask())
    outdir = Path(questionary.text("Output directory:", default=str(DEFAULT_OUTDIR)).ask())

    # Check if directory exists and handle user choice
    while outdir.exists() and outdir.is_dir():
        choice = questionary.select(
            f"Directory '{outdir}' already exists. What would you like to do?",
            choices=[
                {"name": "Overwrite existing files", "value": "o"},
                {"name": "Change output directory", "value": "d"},
                {"name": "Cancel", "value": "q"},
            ],
        ).ask()

        if choice == "q":
            print("Cancelled.")
            return 0
        elif choice == "d":
            outdir = Path(questionary.text("Output directory:", default=str(DEFAULT_OUTDIR)).ask())
        else:  # choice == "o"
            break

    concurrency = int(
        questionary.text("Concurrency:", default=str(provider.default_concurrency)).ask()
    )

    api_key = None
    if provider.requires_api_key:
        env_key = provider.api_key_env or ""
        api_key = os.getenv(env_key)
        if not api_key:
            api_key = questionary.password(f"Enter API key for {provider.display_name}:").ask()

    total = count_tiles_for_regions(regions, 1, max_zoom)
    print(f"Planned tiles: {total}")
    if dry_run:
        print("Dry-run complete.")
        return 0

    proceed = questionary.confirm("Proceed with download?", default=True).ask()
    if not proceed:
        print("Cancelled.")
        return 0

    requests = _requests_for_regions(regions, 1, max_zoom, None)
    url_builder = get_url_builder(provider, api_key=api_key, style=style)
    downloader = TileDownloader(
        outdir, url_builder, headers=provider.headers, concurrent_requests=concurrency
    )
    asyncio.run(downloader.download(requests))
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
