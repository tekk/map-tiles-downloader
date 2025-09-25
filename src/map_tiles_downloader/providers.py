from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


UrlBuilder = Callable[[int, int, int], str]


@dataclass(frozen=True)
class Provider:
    name: str
    display_name: str
    requires_api_key: bool
    api_key_env: Optional[str]
    styles: Optional[List[str]]
    default_style: Optional[str]
    default_concurrency: int
    headers: Dict[str, str]
    build_url: Callable[[int, int, int, Optional[str], Optional[str]], str]


def _thunderforest_url(
    zoom: int, x: int, y: int, style: Optional[str], api_key: Optional[str]
) -> str:
    s = style or "neighbourhood"
    if not api_key:
        raise ValueError("Thunderforest requires an API key")
    return f"https://tile.thunderforest.com/{s}/{zoom}/{x}/{y}.png?apikey={api_key}"


def _osm_url(zoom: int, x: int, y: int, style: Optional[str], api_key: Optional[str]) -> str:
    # OSM standard style server; respect usage policy: low concurrency and fair use
    return f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"


PROVIDERS: Dict[str, Provider] = {
    "thunderforest": Provider(
        name="thunderforest",
        display_name="Thunderforest",
        requires_api_key=True,
        api_key_env="THUNDERFOREST_API_KEY",
        styles=[
            "outdoors",
            "mobile-atlas",
            "cycle",
            "transport",
            "landscape",
            "transport-dark",
            "spinal-map",
            "pioneer",
            "neighbourhood",
            "atlas",
        ],
        default_style="neighbourhood",
        default_concurrency=20,
        headers={},
        build_url=_thunderforest_url,
    ),
    "osm": Provider(
        name="osm",
        display_name="OpenStreetMap (Standard)",
        requires_api_key=False,
        api_key_env=None,
        styles=None,
        default_style=None,
        default_concurrency=2,
        headers={"User-Agent": "map-tiles-downloader/0.1 (respect OSM tile usage policy)"},
        build_url=_osm_url,
    ),
}


def get_url_builder(provider: Provider, api_key: Optional[str], style: Optional[str]) -> UrlBuilder:
    def builder(zoom: int, x: int, y: int) -> str:
        return provider.build_url(zoom, x, y, style, api_key)

    return builder
