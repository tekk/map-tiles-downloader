from map_tiles_downloader.tiling import lon2tilex, lat2tiley, bbox_tile_span


def test_lon2tilex_basic():
    assert lon2tilex(0, 1) == 1
    assert lon2tilex(-180, 1) == 0
    assert lon2tilex(180 - 1e-9, 1) == 3 // 2  # int truncation


def test_bbox_tile_span_monotonic():
    sx, ex, sy, ey = bbox_tile_span(0, 0, 10, 10, 3)
    assert sx <= ex
    assert sy <= ey

