from __future__ import annotations

from typing import Dict, Tuple, Optional, Any, List

import geonamescache

RegionBBox = Tuple[float, float, float, float]
RegionCatalog = Dict[str, Dict[str, Dict[str, RegionBBox]]]


def _parse_country_bbox(country: Dict[str, Any]) -> Optional[RegionBBox]:
    bbox = country.get("bbox")
    if not bbox:
        return None
    try:
        # Try Natural Earth style keys
        west = bbox.get("west")
        south = bbox.get("south")
        east = bbox.get("east")
        north = bbox.get("north")
        if None not in (south, west, north, east):
            return (float(south), float(west), float(north), float(east))
        # Try {min:{lat,lon}, max:{lat,lon}}
        mn = bbox.get("min")
        mx = bbox.get("max")
        if mn and mx:
            return (float(mn["lat"]), float(mn["lon"]), float(mx["lat"]), float(mx["lon"]))
    except Exception:
        return None
    return None


def load_region_catalog() -> RegionCatalog:
    gc = geonamescache.GeonamesCache()

    continents = gc.get_continents()  # code -> {..., 'name': 'Europe'}
    continent_name_by_code: Dict[str, str] = {
        code: data.get("name", code) for code, data in continents.items()
    }

    countries = gc.get_countries()  # mixed-key dict; iterate values
    # Subdivisions are available only in newer geonamescache versions; fallback to empty mapping
    subdivisions_getter = getattr(gc, "get_subdivisions", None)
    subdivisions = subdivisions_getter() if callable(subdivisions_getter) else {}
    cities = (
        gc.get_cities()
    )  # geonameid -> {'countrycode': 'US', 'admin1code': 'CA', 'latitude': '34.1', 'longitude': '-118.3', ...}

    # Build city-derived admin1 bounding boxes per country
    admin1_bbox: Dict[str, Dict[str, List[float]]] = {}
    for city in cities.values():
        try:
            cc = city.get("countrycode")
            a1 = city.get("admin1code")
            lat = float(city.get("latitude"))
            lon = float(city.get("longitude"))
            if not cc or not a1:
                continue
            country_map = admin1_bbox.setdefault(cc, {})
            box = country_map.get(a1)
            if box is None:
                # [south, west, north, east]
                country_map[a1] = [lat, lon, lat, lon]
            else:
                box[0] = min(box[0], lat)
                box[1] = min(box[1], lon)
                box[2] = max(box[2], lat)
                box[3] = max(box[3], lon)
        except Exception:
            continue

    # Build catalog
    catalog: RegionCatalog = {}

    for c in countries.values():
        try:
            continent_code = c.get("continentcode") or "Other"
            continent_name = continent_name_by_code.get(continent_code, continent_code)
            country_name = (
                c.get("name") or c.get("asciiname") or c.get("iso") or c.get("iso3") or "Unknown"
            )
            iso2 = c.get("iso")  # two-letter code

            if continent_name not in catalog:
                catalog[continent_name] = {}

            states: Dict[str, RegionBBox] = {}

            # Use city-derived admin1 boxes where possible
            if iso2 and iso2 in admin1_bbox:
                for a1code, box in admin1_bbox[iso2].items():
                    key = f"{iso2}.{a1code}"
                    sub = subdivisions.get(key) if isinstance(subdivisions, dict) else None
                    state_name = (sub.get("name") if isinstance(sub, dict) else None) or a1code
                    states[state_name] = (
                        float(box[0]),
                        float(box[1]),
                        float(box[2]),
                        float(box[3]),
                    )

            # Ensure a country-wide aggregate exists
            country_box = _parse_country_bbox(c)
            if not country_box and iso2 and iso2 in admin1_bbox and admin1_bbox[iso2]:
                # aggregate from states
                sb = list(admin1_bbox[iso2].values())
                south = min(b[0] for b in sb)
                west = min(b[1] for b in sb)
                north = max(b[2] for b in sb)
                east = max(b[3] for b in sb)
                country_box = (south, west, north, east)

            if country_box:
                states[f"All of {country_name}"] = country_box

            # if still no states computed, at least add country-wide bbox
            if not states and country_box:
                states[country_name] = country_box

            catalog[continent_name][country_name] = states
        except Exception:
            continue

    return catalog
