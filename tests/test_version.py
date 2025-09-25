from importlib.metadata import version


def test_package_version_matches_dunder():
    # Ensure installed distribution version matches module __version__
    import map_tiles_downloader as mtd

    dist_ver = version("map-tiles-downloader")
    assert mtd.__version__ == dist_ver
