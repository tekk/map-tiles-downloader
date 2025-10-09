import platform
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from map_tiles_downloader.cli import build_parser, main, _requests_for_regions, _has_curses


class TestBuildParser:
    def test_parser_creation(self):
        parser = build_parser()
        assert parser is not None
        assert parser.prog == "map-tiles-downloader"

    def test_cli_subcommands_exist(self):
        parser = build_parser()
        # Access argparse internal structure to inspect subcommand names
        subparsers_actions = list(parser._subparsers._group_actions)  # type: ignore[attr-defined]
        assert subparsers_actions, "No subparsers found on CLI parser"
        choices = set(subparsers_actions[0].choices.keys())  # type: ignore[attr-defined]

        # Expected commands - wizard is Windows-only
        expected = {"bbox", "kml", "list", "tui"}
        if platform.system() == "Windows":
            expected.add("wizard")

        missing = expected - choices
        assert not missing, f"Missing CLI subcommands: {missing}"

    def test_bbox_subcommand_args(self):
        parser = build_parser()
        # Test that bbox subcommand can be parsed
        args = parser.parse_args(["bbox", "0", "0", "10", "10"])
        assert args.command == "bbox"
        assert args.south == 0.0
        assert args.west == 0.0
        assert args.north == 10.0
        assert args.east == 10.0
        assert args.max_zoom == 14

    def test_bbox_subcommand_with_options(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "bbox",
                "0",
                "0",
                "10",
                "10",
                "--max-zoom",
                "12",
                "--provider",
                "osm",
                "--api-key",
                "test_key",
                "--outdir",
                "/tmp/test",
                "--concurrency",
                "5",
                "--max-tiles",
                "100",
                "--dry-run",
            ]
        )
        assert args.command == "bbox"
        assert args.max_zoom == 12
        assert args.provider == "osm"
        assert args.api_key == "test_key"
        assert args.outdir == Path("/tmp/test")
        assert args.concurrency == 5
        assert args.max_tiles == 100
        assert args.dry_run is True

    def test_kml_subcommand_args(self):
        parser = build_parser()
        args = parser.parse_args(["kml", "test.kml"])
        assert args.command == "kml"
        assert str(args.kmlfile) == "test.kml"
        assert args.latrgn == 0.1
        assert args.lonrgn == 0.1

    def test_kml_subcommand_with_options(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "kml",
                "test.kml",
                "--latrgn",
                "0.5",
                "--lonrgn",
                "0.5",
                "--max-zoom",
                "10",
                "--provider",
                "thunderforest",
                "--api-key",
                "test_key",
            ]
        )
        assert args.command == "kml"
        assert args.latrgn == 0.5
        assert args.lonrgn == 0.5
        assert args.max_zoom == 10

    def test_list_subcommand_providers(self):
        parser = build_parser()
        args = parser.parse_args(["list", "providers"])
        assert args.command == "list"
        assert args.what == "providers"

    def test_list_subcommand_regions(self):
        parser = build_parser()
        args = parser.parse_args(["list", "regions"])
        assert args.command == "list"
        assert args.what == "regions"

    def test_tui_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["tui"])
        assert args.command == "tui"
        assert args.no_colors is False  # Default should be False (colors enabled)

    def test_tui_subcommand_no_colors(self):
        parser = build_parser()
        args = parser.parse_args(["tui", "--no-colors"])
        assert args.command == "tui"
        assert args.no_colors is True

    @pytest.mark.skipif(
        platform.system() != "Windows", reason="Wizard command only available on Windows"
    )
    def test_wizard_subcommand_windows(self):
        parser = build_parser()
        args = parser.parse_args(["wizard"])
        assert args.command == "wizard"

    def test_invalid_provider(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["bbox", "0", "0", "10", "10", "--provider", "invalid"])

    def test_invalid_log_level(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["bbox", "0", "0", "10", "10", "--log-level", "INVALID"])


class TestRequestsForRegions:
    def test_requests_for_regions_basic(self):
        regions = {"test": (0, 0, 10, 10)}
        requests = _requests_for_regions(regions, 1, 2, None)
        assert len(requests) > 0
        for req in requests:
            assert hasattr(req, "zoom")
            assert hasattr(req, "x")
            assert hasattr(req, "y")

    def test_requests_for_regions_with_max_tiles(self):
        regions = {"test": (0, 0, 10, 10)}
        requests = _requests_for_regions(regions, 1, 5, 10)
        assert len(requests) <= 10

    def test_requests_for_regions_empty(self):
        requests = _requests_for_regions({}, 1, 2, None)
        assert len(requests) == 0


class TestMainFunction:
    def test_main_help(self):
        with pytest.raises(SystemExit):
            main(["--help"])

    @patch("map_tiles_downloader.cli._run_wizard")
    @patch("map_tiles_downloader.cli.main_tui")
    def test_main_no_args(self, mock_tui, mock_wizard):
        mock_tui.return_value = 0
        mock_wizard.return_value = 0
        result = main([])
        assert result == 0
        if _has_curses():
            mock_tui.assert_called_once_with()
            mock_wizard.assert_not_called()
        else:
            mock_wizard.assert_called_once_with()
            mock_tui.assert_not_called()

    def test_main_wizard_non_windows(self):
        if platform.system() != "Windows":
            with pytest.raises(SystemExit) as exc_info:
                main(["wizard"])
            assert exc_info.value.code == 2  # argparse exit code for invalid choice

    @patch("map_tiles_downloader.cli._run_wizard")
    @patch("map_tiles_downloader.cli.main_tui")
    @patch("platform.system")
    def test_main_wizard_windows(self, mock_platform, mock_tui, mock_wizard):
        mock_platform.return_value = "Windows"
        # Force TUI to fail so it falls back to wizard
        mock_tui.side_effect = Exception("Simulated TUI failure")
        mock_wizard.return_value = 0
        result = main(["wizard", "--dry-run"])
        assert result == 0
        mock_wizard.assert_called_once_with(dry_run=True)

    @patch("map_tiles_downloader.cli.count_tiles_for_regions")
    @patch("map_tiles_downloader.cli.PROVIDERS")
    @patch("os.getenv")
    @patch("builtins.print")
    def test_main_bbox_dry_run(self, mock_print, mock_getenv, mock_providers, mock_count):
        mock_count.return_value = 42
        mock_provider = MagicMock()
        mock_provider.api_key_env = "TEST_API_KEY"
        mock_provider.requires_api_key = False
        mock_provider.default_style = "test_style"
        mock_provider.headers = {}
        mock_provider.default_concurrency = 10
        mock_providers.__getitem__.return_value = mock_provider

        result = main(["bbox", "0", "0", "10", "10", "--dry-run"])
        assert result == 0
        mock_print.assert_called_with("Planned tiles: 42", flush=True)

    @patch("map_tiles_downloader.cli.kml_to_regions")
    @patch("map_tiles_downloader.cli.count_tiles_for_regions")
    @patch("map_tiles_downloader.cli.PROVIDERS")
    @patch("os.getenv")
    @patch("builtins.print")
    def test_main_kml_dry_run(
        self, mock_print, mock_getenv, mock_providers, mock_count, mock_kml_to_regions
    ):
        mock_kml_to_regions.return_value = {"test": (0, 0, 10, 10)}
        mock_count.return_value = 24
        mock_provider = MagicMock()
        mock_provider.api_key_env = "TEST_API_KEY"
        mock_provider.requires_api_key = False
        mock_provider.default_style = "test_style"
        mock_provider.headers = {}
        mock_provider.default_concurrency = 10
        mock_providers.__getitem__.return_value = mock_provider

        result = main(["kml", "test.kml", "--dry-run"])
        assert result == 0
        mock_print.assert_called_with("Planned tiles: 24", flush=True)

    @patch("map_tiles_downloader.cli.load_region_catalog")
    @patch("builtins.print")
    def test_main_list_providers(self, mock_print, mock_load_catalog):
        from map_tiles_downloader.cli import PROVIDERS

        result = main(["list", "providers"])
        assert result == 0
        # Should have printed provider info
        assert mock_print.call_count == len(PROVIDERS)

    @patch("map_tiles_downloader.cli.load_region_catalog")
    @patch("builtins.print")
    def test_main_list_regions(self, mock_print, mock_load_catalog):
        mock_catalog = {"Continent1": {"Country1": {"State1": (0, 0, 10, 10)}}}
        mock_load_catalog.return_value = mock_catalog
        result = main(["list", "regions"])
        assert result == 0
        # Should print continent, country, and state
        assert mock_print.call_count >= 3

    @patch("map_tiles_downloader.cli.main_tui")
    def test_main_tui(self, mock_main_tui):
        mock_main_tui.return_value = 0
        result = main(["tui"])
        assert result == 0
        mock_main_tui.assert_called_once_with(colors_enabled=True)

    @patch("map_tiles_downloader.cli.main_tui")
    def test_main_tui_no_colors(self, mock_main_tui):
        mock_main_tui.return_value = 0
        result = main(["tui", "--no-colors"])
        assert result == 0
        mock_main_tui.assert_called_once_with(colors_enabled=False)
