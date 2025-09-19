from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Tuple

from fastkml import Placemark, Point, LineString, kml
from fastkml.utils import find_all as kml_find_all


def _parse_kml_file(kmlfile: Path) -> kml.KML:
    try:
        return kml.KML.parse(kmlfile)
    except Exception:
        k = kml.KML()
        text = Path(kmlfile).read_text(encoding="utf-8")
        k.from_string(text)
        return k


def expand_gps(lat: float, lon: float, latrgn: float, lonrgn: float) -> Tuple[float, float, float, float]:
    return (lat - latrgn, lon - lonrgn, lat + latrgn, lon + lonrgn)


def kml_to_regions(kmlfile: Path, latrgn: float = 0.1, lonrgn: float = 0.1) -> Dict[str, Tuple[float, float, float, float]]:
    resdict: Dict[str, Tuple[float, float, float, float]] = {}
    k = _parse_kml_file(kmlfile)
    pmarks = list(kml_find_all(k, of_type=Placemark))
    for p in pmarks:
        pts = list(kml_find_all(p, of_type=Point))
        if len(pts) == 1:
            coord = pts[0].kml_coordinates.coords[0]
            lon = coord[0]
            lat = coord[1]
            resdict[p.name] = expand_gps(lat, lon, latrgn, lonrgn)
        else:
            coord_idx = 0
            lstrs = list(kml_find_all(p, of_type=LineString))
            for lstr in lstrs:
                for coord in lstr.kml_coordinates.coords:
                    lon = coord[0]
                    lat = coord[1]
                    name = f"{p.name}_{coord_idx:06}"
                    resdict[name] = expand_gps(lat, lon, latrgn, lonrgn)
                    coord_idx += 1
    return resdict


