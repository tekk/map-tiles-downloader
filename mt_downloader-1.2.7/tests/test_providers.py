import pytest
from map_tiles_downloader.providers import (
    Provider,
    PROVIDERS,
    get_url_builder,
    _thunderforest_url,
    _osm_url,
)


class TestURLBuilders:
    def test_thunderforest_url_basic(self):
        url = _thunderforest_url(10, 123, 456, "neighbourhood", "test_api_key")
        expected = "https://tile.thunderforest.com/neighbourhood/10/123/456.png?apikey=test_api_key"
        assert url == expected

    def test_thunderforest_url_default_style(self):
        url = _thunderforest_url(5, 1, 2, None, "key123")
        expected = "https://tile.thunderforest.com/neighbourhood/5/1/2.png?apikey=key123"
        assert url == expected

    def test_thunderforest_url_missing_api_key(self):
        with pytest.raises(ValueError, match="Thunderforest requires an API key"):
            _thunderforest_url(1, 0, 0, "atlas", None)

    def test_osm_url_basic(self):
        url = _osm_url(8, 100, 200, None, None)
        expected = "https://tile.openstreetmap.org/8/100/200.png"
        assert url == expected

    def test_osm_url_ignores_api_key_and_style(self):
        # OSM URL builder should ignore API key and style parameters
        url = _osm_url(12, 50, 75, "some_style", "some_key")
        expected = "https://tile.openstreetmap.org/12/50/75.png"
        assert url == expected


class TestProviderClass:
    def test_provider_creation(self):
        provider = Provider(
            name="test_provider",
            display_name="Test Provider",
            requires_api_key=True,
            api_key_env="TEST_API_KEY",
            styles=["style1", "style2"],
            default_style="style1",
            default_concurrency=5,
            headers={"User-Agent": "test"},
            build_url=_osm_url,
        )
        assert provider.name == "test_provider"
        assert provider.display_name == "Test Provider"
        assert provider.requires_api_key is True
        assert provider.api_key_env == "TEST_API_KEY"
        assert provider.styles == ["style1", "style2"]
        assert provider.default_style == "style1"
        assert provider.default_concurrency == 5
        assert provider.headers == {"User-Agent": "test"}
        assert provider.build_url == _osm_url

    def test_provider_frozen(self):
        provider = Provider(
            name="test",
            display_name="Test",
            requires_api_key=False,
            api_key_env=None,
            styles=None,
            default_style=None,
            default_concurrency=10,
            headers={},
            build_url=_osm_url,
        )
        # Should not be able to modify frozen dataclass
        with pytest.raises(AttributeError):
            provider.name = "modified"


class TestProvidersDict:
    def test_thunderforest_provider(self):
        tf = PROVIDERS["thunderforest"]
        assert tf.name == "thunderforest"
        assert tf.display_name == "Thunderforest"
        assert tf.requires_api_key is True
        assert tf.api_key_env == "THUNDERFOREST_API_KEY"
        assert isinstance(tf.styles, list)
        assert "neighbourhood" in tf.styles
        assert tf.default_style == "neighbourhood"
        assert tf.default_concurrency == 20
        assert tf.build_url == _thunderforest_url

    def test_osm_provider(self):
        osm = PROVIDERS["osm"]
        assert osm.name == "osm"
        assert osm.display_name == "OpenStreetMap (Standard)"
        assert osm.requires_api_key is False
        assert osm.api_key_env is None
        assert osm.styles is None
        assert osm.default_style is None
        assert osm.default_concurrency == 2
        assert "User-Agent" in osm.headers
        assert osm.build_url == _osm_url

    def test_all_providers_have_required_attributes(self):
        for name, provider in PROVIDERS.items():
            assert isinstance(provider, Provider)
            assert provider.name == name
            assert isinstance(provider.display_name, str)
            assert isinstance(provider.requires_api_key, bool)
            assert isinstance(provider.default_concurrency, int)
            assert isinstance(provider.headers, dict)
            assert callable(provider.build_url)


class TestGetURLBuilder:
    def test_get_url_builder_thunderforest_with_api_key(self):
        tf = PROVIDERS["thunderforest"]
        builder = get_url_builder(tf, api_key="test_key", style="atlas")
        url = builder(5, 10, 20)
        expected = "https://tile.thunderforest.com/atlas/5/10/20.png?apikey=test_key"
        assert url == expected

    def test_get_url_builder_thunderforest_default_style(self):
        tf = PROVIDERS["thunderforest"]
        builder = get_url_builder(tf, api_key="test_key", style=None)
        url = builder(3, 1, 2)
        expected = "https://tile.thunderforest.com/neighbourhood/3/1/2.png?apikey=test_key"
        assert url == expected

    def test_get_url_builder_osm(self):
        osm = PROVIDERS["osm"]
        builder = get_url_builder(osm, api_key=None, style=None)
        url = builder(7, 15, 25)
        expected = "https://tile.openstreetmap.org/7/15/25.png"
        assert url == expected

    def test_get_url_builder_osm_ignores_params(self):
        osm = PROVIDERS["osm"]
        builder = get_url_builder(osm, api_key="ignored", style="ignored")
        url = builder(1, 0, 0)
        expected = "https://tile.openstreetmap.org/1/0/0.png"
        assert url == expected

    def test_get_url_builder_thunderforest_missing_api_key_in_build_url(self):
        tf = PROVIDERS["thunderforest"]
        builder = get_url_builder(tf, api_key=None, style="atlas")
        with pytest.raises(ValueError, match="Thunderforest requires an API key"):
            builder(1, 0, 0)


class TestProviderIntegration:
    """Integration tests combining providers and URL builders"""

    @pytest.mark.parametrize(
        "provider_key,zoom,x,y,expected_contains",
        [
            ("thunderforest", 10, 123, 456, "tile.thunderforest.com"),
            ("osm", 8, 100, 200, "tile.openstreetmap.org"),
        ],
    )
    def test_provider_url_patterns(self, provider_key, zoom, x, y, expected_contains):
        provider = PROVIDERS[provider_key]
        api_key = "test_key" if provider.requires_api_key else None
        builder = get_url_builder(provider, api_key=api_key, style=provider.default_style)
        url = builder(zoom, x, y)
        assert expected_contains in url
        assert f"/{zoom}/{x}/{y}.png" in url

    def test_thunderforest_styles(self):
        tf = PROVIDERS["thunderforest"]
        expected_styles = {
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
        }
        assert set(tf.styles) == expected_styles

    def test_osm_no_styles(self):
        osm = PROVIDERS["osm"]
        assert osm.styles is None
        assert osm.default_style is None
