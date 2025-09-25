from unittest.mock import patch, MagicMock
from map_tiles_downloader.regions import _parse_country_bbox, load_region_catalog


class TestParseCountryBbox:
    def test_parse_country_bbox_natural_earth_style(self):
        country = {"bbox": {"west": -10.0, "south": 35.0, "east": 5.0, "north": 45.0}}
        result = _parse_country_bbox(country)
        assert result == (35.0, -10.0, 45.0, 5.0)  # south, west, north, east

    def test_parse_country_bbox_min_max_style(self):
        country = {"bbox": {"min": {"lat": 35.0, "lon": -10.0}, "max": {"lat": 45.0, "lon": 5.0}}}
        result = _parse_country_bbox(country)
        assert result == (35.0, -10.0, 45.0, 5.0)

    def test_parse_country_bbox_missing_bbox(self):
        country = {}
        result = _parse_country_bbox(country)
        assert result is None

    def test_parse_country_bbox_missing_keys(self):
        country = {"bbox": {"west": -10.0}}  # Missing other keys
        result = _parse_country_bbox(country)
        assert result is None

    def test_parse_country_bbox_invalid_data(self):
        country = {"bbox": {"west": "invalid", "south": 35.0, "east": 5.0, "north": 45.0}}
        result = _parse_country_bbox(country)
        assert result is None


class TestLoadRegionCatalog:
    @patch("map_tiles_downloader.regions.geonamescache")
    def test_load_region_catalog_basic_structure(self, mock_geonamescache):
        # Mock geonamescache data
        mock_gc = MagicMock()
        mock_geonamescache.GeonamesCache.return_value = mock_gc

        # Mock continents
        mock_gc.get_continents.return_value = {
            "EU": {"name": "Europe"},
            "NA": {"name": "North America"},
        }

        # Mock countries (should be dict with country codes as keys)
        mock_gc.get_countries.return_value = {
            "FR": {
                "continentcode": "EU",
                "name": "France",
                "iso": "FR",
                "bbox": {"west": -5.0, "south": 41.0, "east": 10.0, "north": 51.0},
            },
            "US": {
                "continentcode": "NA",
                "name": "United States",
                "iso": "US",
                "bbox": {"west": -125.0, "south": 25.0, "east": -65.0, "north": 50.0},
            },
        }

        # Mock subdivisions (newer geonamescache versions)
        mock_gc.get_subdivisions.return_value = {
            "US.CA": {"name": "California"},
            "US.NY": {"name": "New York"},
        }

        # Mock cities for admin1 bbox calculation
        mock_gc.get_cities.return_value = {
            "1": {
                "countrycode": "US",
                "admin1code": "CA",
                "latitude": "36.7783",
                "longitude": "-119.4179",
            },
            "2": {
                "countrycode": "US",
                "admin1code": "NY",
                "latitude": "40.7128",
                "longitude": "-74.0060",
            },
        }

        catalog = load_region_catalog()

        # Check structure
        assert isinstance(catalog, dict)
        assert "Europe" in catalog
        assert "North America" in catalog

        # Check countries exist
        assert "France" in catalog["Europe"]
        assert "United States" in catalog["North America"]

    @patch("map_tiles_downloader.regions.geonamescache")
    def test_load_region_catalog_handles_missing_subdivisions(self, mock_geonamescache):
        # Test fallback when subdivisions getter is not available (older geonamescache)
        mock_gc = MagicMock()
        mock_geonamescache.GeonamesCache.return_value = mock_gc

        # Mock continents
        mock_gc.get_continents.return_value = {"EU": {"name": "Europe"}}

        # Mock countries
        mock_gc.get_countries.return_value = {
            "FR": {
                "continentcode": "EU",
                "name": "France",
                "iso": "FR",
                "bbox": {"west": -5.0, "south": 41.0, "east": 10.0, "north": 51.0},
            }
        }

        # Mock subdivisions getter as None (older versions)
        mock_gc.get_subdivisions = None

        # Mock cities
        mock_gc.get_cities.return_value = {}

        catalog = load_region_catalog()

        # Should still work without subdivisions
        assert "Europe" in catalog
        assert "France" in catalog["Europe"]

    @patch("map_tiles_downloader.regions.geonamescache")
    def test_load_region_catalog_handles_exceptions(self, mock_geonamescache):
        # Test that exceptions in processing don't break the whole catalog
        mock_gc = MagicMock()
        mock_geonamescache.GeonamesCache.return_value = mock_gc

        mock_gc.get_continents.return_value = {"EU": {"name": "Europe"}}

        # One good country, one that will cause an exception
        mock_gc.get_countries.return_value = {
            "FR": {
                "continentcode": "EU",
                "name": "France",
                "iso": "FR",
                "bbox": {"west": -5.0, "south": 41.0, "east": 10.0, "north": 51.0},
            },
            "BAD": {
                "continentcode": "EU",
                "name": None,  # This will cause issues
                "iso": None,
                "bbox": None,
            },
        }

        mock_gc.get_subdivisions.return_value = {}
        mock_gc.get_cities.return_value = {}

        catalog = load_region_catalog()

        # Should still have France despite the problematic country
        assert "Europe" in catalog
        assert "France" in catalog["Europe"]

    @patch("map_tiles_downloader.regions.geonamescache")
    def test_load_region_catalog_city_bbox_aggregation(self, mock_geonamescache):
        # Test the city-based bbox aggregation for admin1 regions
        mock_gc = MagicMock()
        mock_geonamescache.GeonamesCache.return_value = mock_gc

        mock_gc.get_continents.return_value = {"NA": {"name": "North America"}}

        mock_gc.get_countries.return_value = {
            "US": {"continentcode": "NA", "name": "United States", "iso": "US"}
        }

        mock_gc.get_subdivisions.return_value = {
            "US.CA": {"name": "California"},
            "US.TX": {"name": "Texas"},
        }

        # Cities for California and Texas
        mock_gc.get_cities.return_value = {
            "1": {
                "countrycode": "US",
                "admin1code": "CA",
                "latitude": "36.0",
                "longitude": "-120.0",
            },
            "2": {
                "countrycode": "US",
                "admin1code": "CA",
                "latitude": "38.0",
                "longitude": "-118.0",
            },
            "3": {
                "countrycode": "US",
                "admin1code": "TX",
                "latitude": "31.0",
                "longitude": "-100.0",
            },
            "4": {
                "countrycode": "US",
                "admin1code": "TX",
                "latitude": "33.0",
                "longitude": "-98.0",
            },
        }

        catalog = load_region_catalog()

        assert "North America" in catalog
        assert "United States" in catalog["North America"]

        us_states = catalog["North America"]["United States"]

        # Should have California and Texas with aggregated bboxes
        assert "California" in us_states
        assert "Texas" in us_states

        # Check California bbox (south: 36.0, west: -120.0, north: 38.0, east: -118.0)
        ca_bbox = us_states["California"]
        assert ca_bbox[0] == 36.0  # south
        assert ca_bbox[1] == -120.0  # west
        assert ca_bbox[2] == 38.0  # north
        assert ca_bbox[3] == -118.0  # east

    @patch("map_tiles_downloader.regions.geonamescache")
    def test_load_region_catalog_fallback_country_bbox(self, mock_geonamescache):
        # Test fallback to country-wide bbox when no states are computed
        mock_gc = MagicMock()
        mock_geonamescache.GeonamesCache.return_value = mock_gc

        mock_gc.get_continents.return_value = {"EU": {"name": "Europe"}}

        mock_gc.get_countries.return_value = {
            "MC": {
                "continentcode": "EU",
                "name": "Monaco",
                "iso": "MC",
                "bbox": {"west": 7.4, "south": 43.7, "east": 7.4, "north": 43.8},
            }
        }

        mock_gc.get_subdivisions.return_value = {}
        mock_gc.get_cities.return_value = {}  # No cities for Monaco

        catalog = load_region_catalog()

        assert "Europe" in catalog
        assert "Monaco" in catalog["Europe"]

        monaco_states = catalog["Europe"]["Monaco"]
        # Should have "All of Monaco" as fallback
        assert "All of Monaco" in monaco_states
        assert monaco_states["All of Monaco"] == (43.7, 7.4, 43.8, 7.4)


class TestRegionCatalogStructure:
    """Test the structure and types of the loaded catalog"""

    @patch("map_tiles_downloader.regions.geonamescache")
    def test_catalog_type_annotations(self, mock_geonamescache):
        # Ensure the catalog matches the expected type structure
        mock_gc = MagicMock()
        mock_geonamescache.GeonamesCache.return_value = mock_gc

        mock_gc.get_continents.return_value = {"EU": {"name": "Europe"}}
        mock_gc.get_countries.return_value = {
            "FR": {
                "continentcode": "EU",
                "name": "France",
                "iso": "FR",
                "bbox": {"west": -5.0, "south": 41.0, "east": 10.0, "north": 51.0},
            }
        }
        mock_gc.get_subdivisions.return_value = {}
        mock_gc.get_cities.return_value = {}

        catalog = load_region_catalog()

        # Check types
        assert isinstance(catalog, dict)

        for continent, countries in catalog.items():
            assert isinstance(continent, str)
            assert isinstance(countries, dict)

            for country, states in countries.items():
                assert isinstance(country, str)
                assert isinstance(states, dict)

                for state, bbox in states.items():
                    assert isinstance(state, str)
                    assert isinstance(bbox, tuple)
                    assert len(bbox) == 4
                    assert all(isinstance(coord, float) for coord in bbox)
