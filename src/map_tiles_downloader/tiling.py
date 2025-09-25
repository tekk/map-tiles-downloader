from __future__ import annotations

from math import log, tan, cos, pi
from typing import Dict, Generator, Tuple


def lon2tilex(lon: float, zoom: int) -> int:
    return int((lon + 180.0) / 360.0 * (1 << zoom))


def lat2tiley(lat: float, zoom: int) -> int:
    return int(
        (1.0 - log(tan(lat * pi / 180.0) + 1.0 / cos(lat * pi / 180.0)) / pi) / 2.0 * (1 << zoom)
    )


def normalize_bbox(
    south: float, west: float, north: float, east: float
) -> Tuple[float, float, float, float]:
    min_lat = min(south, north)
    max_lat = max(south, north)
    min_lon = min(west, east)
    max_lon = max(west, east)
    return (min_lat, min_lon, max_lat, max_lon)


def bbox_tile_span(
    south: float, west: float, north: float, east: float, zoom: int
) -> Tuple[int, int, int, int]:
    min_lat, min_lon, max_lat, max_lon = normalize_bbox(south, west, north, east)
    start_x = lon2tilex(min_lon, zoom)
    end_x = lon2tilex(max_lon, zoom)
    start_y = lat2tiley(max_lat, zoom)
    end_y = lat2tiley(min_lat, zoom)
    return start_x, end_x, start_y, end_y


def iter_tiles_for_bbox(
    south: float, west: float, north: float, east: float, zoom: int
) -> Generator[Tuple[int, int, int], None, None]:
    start_x, end_x, start_y, end_y = bbox_tile_span(south, west, north, east, zoom)
    for x in range(start_x, end_x + 1):
        for y in range(start_y, end_y + 1):
            yield (zoom, x, y)


def count_tiles_for_bbox(
    south: float, west: float, north: float, east: float, min_zoom: int, max_zoom: int
) -> int:
    total = 0
    for zoom in range(min_zoom, max_zoom + 1):
        start_x, end_x, start_y, end_y = bbox_tile_span(south, west, north, east, zoom)
        total += (end_x - start_x + 1) * (end_y - start_y + 1)
    return total


def count_tiles_for_regions(
    regions: Dict[str, Tuple[float, float, float, float]], min_zoom: int, max_zoom: int
) -> int:
    total = 0
    for south, west, north, east in regions.values():
        total += count_tiles_for_bbox(south, west, north, east, min_zoom, max_zoom)
    return total
