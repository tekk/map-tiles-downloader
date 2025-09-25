import tempfile
from pathlib import Path
import pytest
from map_tiles_downloader.kml_regions import _parse_kml_file, expand_gps, kml_to_regions


class TestExpandGPS:
    def test_expand_gps_basic(self):
        result = expand_gps(45.0, -122.0, 0.1, 0.1)
        expected = (44.9, -122.1, 45.1, -121.9)  # south, west, north, east
        assert result == expected

    def test_expand_gps_zero_expansion(self):
        result = expand_gps(45.0, -122.0, 0.0, 0.0)
        expected = (45.0, -122.0, 45.0, -122.0)
        assert result == expected

    def test_expand_gps_large_expansion(self):
        result = expand_gps(45.0, -122.0, 1.0, 2.0)
        expected = (44.0, -124.0, 46.0, -120.0)
        assert result == expected

    @pytest.mark.parametrize(
        "lat,lon,latrgn,lonrgn,expected",
        [
            (0, 0, 0.1, 0.1, (-0.1, -0.1, 0.1, 0.1)),
            (90, 180, 0.5, 1.0, (89.5, 179.0, 90.5, 181.0)),
            (-90, -180, 0.2, 0.3, (-90.2, -180.3, -89.8, -179.7)),
        ],
    )
    def test_expand_gps_parametrized(self, lat, lon, latrgn, lonrgn, expected):
        result = expand_gps(lat, lon, latrgn, lonrgn)
        assert result == expected


class TestParseKMLFile:
    def test_parse_kml_file_from_path(self):
        # Create a simple KML file
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Point</name>
      <Point>
        <coordinates>-122.0,45.0,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
            f.write(kml_content)
            f.flush()
            kml_path = Path(f.name)

        try:
            kml_obj = _parse_kml_file(kml_path)
            assert kml_obj is not None
            # Check that it has the expected structure (fastkml uses features list)
            assert hasattr(kml_obj, "features")
            assert len(kml_obj.features) > 0
        finally:
            kml_path.unlink()

    def test_parse_kml_file_invalid_content(self):
        # Test with invalid KML content
        invalid_kml = """<?xml version="1.0"?>
<not-kml>
  <invalid>content</invalid>
</not-kml>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
            f.write(invalid_kml)
            f.flush()
            kml_path = Path(f.name)

        try:
            # fastkml may log errors but still return a KML object
            kml_obj = _parse_kml_file(kml_path)
            assert kml_obj is not None
            # May have empty features due to invalid content
            assert hasattr(kml_obj, "features")
        finally:
            kml_path.unlink()

    def test_parse_kml_file_nonexistent_file(self):
        nonexistent = Path("/nonexistent/file.kml")
        with pytest.raises(FileNotFoundError):
            _parse_kml_file(nonexistent)


class TestKMLToRegions:
    def test_kml_to_regions_single_point(self):
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Point</name>
      <Point>
        <coordinates>-122.0,45.0,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
            f.write(kml_content)
            f.flush()
            kml_path = Path(f.name)

        try:
            regions = kml_to_regions(kml_path, latrgn=0.1, lonrgn=0.1)
            assert len(regions) == 1
            assert "Test Point" in regions
            bbox = regions["Test Point"]
            # Should be expanded around the point
            assert bbox[0] < 45.0  # south
            assert bbox[1] < -122.0  # west
            assert bbox[2] > 45.0  # north
            assert bbox[3] > -122.0  # east
        finally:
            kml_path.unlink()

    def test_kml_to_regions_multiple_points(self):
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Point 1</name>
      <Point>
        <coordinates>-122.0,45.0,0</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Point 2</name>
      <Point>
        <coordinates>-121.0,46.0,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
            f.write(kml_content)
            f.flush()
            kml_path = Path(f.name)

        try:
            regions = kml_to_regions(kml_path, latrgn=0.1, lonrgn=0.1)
            assert len(regions) == 2
            assert "Point 1" in regions
            assert "Point 2" in regions
        finally:
            kml_path.unlink()

    def test_kml_to_regions_path_linestring(self):
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Path</name>
      <LineString>
        <coordinates>
          -122.0,45.0,0
          -121.5,45.2,0
          -121.0,45.5,0
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
            f.write(kml_content)
            f.flush()
            kml_path = Path(f.name)

        try:
            regions = kml_to_regions(kml_path, latrgn=0.1, lonrgn=0.1)
            # Should create regions for each coordinate in the path
            assert len(regions) == 3
            # Check that names are generated as base_name + index
            expected_names = ["Test Path_000000", "Test Path_000001", "Test Path_000002"]
            for name in expected_names:
                assert name in regions
        finally:
            kml_path.unlink()

    def test_kml_to_regions_mixed_content(self):
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Point A</name>
      <Point>
        <coordinates>-122.0,45.0,0</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Path B</name>
      <LineString>
        <coordinates>
          -121.0,46.0,0
          -120.5,46.2,0
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
            f.write(kml_content)
            f.flush()
            kml_path = Path(f.name)

        try:
            regions = kml_to_regions(kml_path, latrgn=0.1, lonrgn=0.1)
            assert len(regions) == 3  # 1 point + 2 path coordinates
            assert "Point A" in regions
            assert "Path B_000000" in regions
            assert "Path B_000001" in regions
        finally:
            kml_path.unlink()

    def test_kml_to_regions_empty_placemarks(self):
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Empty Point</name>
      <Point>
        <coordinates></coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Valid Point</name>
      <Point>
        <coordinates>-122.0,45.0,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
            f.write(kml_content)
            f.flush()
            kml_path = Path(f.name)

        try:
            regions = kml_to_regions(kml_path, latrgn=0.1, lonrgn=0.1)
            # Should only include the valid point
            assert len(regions) == 1
            assert "Valid Point" in regions
            assert "Empty Point" not in regions
        finally:
            kml_path.unlink()

    def test_kml_to_regions_custom_expansion(self):
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test</name>
      <Point>
        <coordinates>-122.0,45.0,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
            f.write(kml_content)
            f.flush()
            kml_path = Path(f.name)

        try:
            regions = kml_to_regions(kml_path, latrgn=0.5, lonrgn=1.0)
            assert len(regions) == 1
            bbox = regions["Test"]
            # Check expansion: 0.5 lat, 1.0 lon
            assert abs(bbox[0] - (45.0 - 0.5)) < 0.001  # south
            assert abs(bbox[1] - (-122.0 - 1.0)) < 0.001  # west
            assert abs(bbox[2] - (45.0 + 0.5)) < 0.001  # north
            assert abs(bbox[3] - (-122.0 + 1.0)) < 0.001  # east
        finally:
            kml_path.unlink()

    def test_kml_to_regions_no_name_fallback(self):
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <Point>
        <coordinates>-122.0,45.0,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".kml", delete=False) as f:
            f.write(kml_content)
            f.flush()
            kml_path = Path(f.name)

        try:
            regions = kml_to_regions(kml_path, latrgn=0.1, lonrgn=0.1)
            assert len(regions) == 1
            assert "point" in regions  # fallback name
        finally:
            kml_path.unlink()
