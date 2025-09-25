import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from map_tiles_downloader.downloader import TileDownloader, TileRequest


class TestTileRequest:
    def test_tile_request_creation(self):
        req = TileRequest(zoom=10, x=123, y=456)
        assert req.zoom == 10
        assert req.x == 123
        assert req.y == 456
        assert req.area_label is None

    def test_tile_request_with_label(self):
        req = TileRequest(zoom=5, x=10, y=20, area_label="Test Area")
        assert req.zoom == 5
        assert req.x == 10
        assert req.y == 20
        assert req.area_label == "Test Area"


class TestTileDownloaderInit:
    def test_init_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def url_builder(z, x, y):
                return f"https://example.com/{z}/{x}/{y}.png"

            downloader = TileDownloader(output_dir, url_builder)

            assert downloader.output_dir == output_dir
            assert downloader.url_builder == url_builder
            assert downloader.headers == {}
            assert downloader.concurrent_requests == 20
            assert downloader.request_timeout_seconds == 10.0
            assert downloader.retry_attempts == 3
            assert downloader.inter_request_delay_seconds == 0.05
            assert downloader.paused is False
            assert downloader.cancelled is False

    def test_init_with_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def url_builder(z, x, y):
                return f"https://example.com/{z}/{x}/{y}.png"

            headers = {"User-Agent": "test"}
            concurrent_requests = 5
            timeout = 30.0
            retries = 5
            delay = 0.1

            downloader = TileDownloader(
                output_dir=output_dir,
                url_builder=url_builder,
                headers=headers,
                concurrent_requests=concurrent_requests,
                request_timeout_seconds=timeout,
                retry_attempts=retries,
                inter_request_delay_seconds=delay,
            )

            assert downloader.output_dir == output_dir
            assert downloader.url_builder == url_builder
            assert downloader.headers == headers
            assert downloader.concurrent_requests == concurrent_requests
            assert downloader.request_timeout_seconds == timeout
            assert downloader.retry_attempts == retries
            assert downloader.inter_request_delay_seconds == delay

    def test_init_creates_output_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "nested" / "deep" / "output"
            assert not output_dir.exists()

            def url_builder(z, x, y):
                return f"https://example.com/{z}/{x}/{y}.png"

            TileDownloader(output_dir, url_builder)

            assert output_dir.exists()
            assert output_dir.is_dir()


class TestTileDownloaderPaths:
    def test_tile_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def url_builder(z, x, y):
                return f"https://tiles.example.com/{z}/{x}/{y}.png"

            downloader = TileDownloader(output_dir, url_builder)

            url = downloader._tile_url(10, 123, 456)
            assert url == "https://tiles.example.com/10/123/456.png"

    def test_tile_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def url_builder(z, x, y):
                return f"https://example.com/{z}/{x}/{y}.png"

            downloader = TileDownloader(output_dir, url_builder)

            path = downloader._tile_path(5, 10, 20)
            expected = output_dir / "5" / "10" / "20.png"
            assert path == expected


class TestTileDownloaderDownloadOne:
    @pytest.mark.asyncio
    async def test_download_one_skip_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def url_builder(z, x, y):
                return f"https://example.com/{z}/{x}/{y}.png"

            downloader = TileDownloader(output_dir, url_builder)

            # Create existing file
            tile_path = output_dir / "5" / "10" / "20.png"
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            tile_path.write_text("existing")

            mock_session = AsyncMock()
            semaphore = asyncio.Semaphore(1)
            req = TileRequest(zoom=5, x=10, y=20)
            pbar = MagicMock()
            on_progress = MagicMock()

            result = await downloader._download_one(mock_session, semaphore, req, pbar, on_progress)

            assert result is True
            # Should not have made HTTP request
            mock_session.get.assert_not_called()
            pbar.update.assert_called_once_with(1)
            on_progress.assert_called_once_with("skipped", req, 0)

    @pytest.mark.asyncio
    async def test_download_one_cancel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def url_builder(z, x, y):
                return f"https://example.com/{z}/{x}/{y}.png"

            downloader = TileDownloader(output_dir, url_builder)

            mock_session = AsyncMock()
            semaphore = asyncio.Semaphore(1)
            req = TileRequest(zoom=5, x=10, y=20)
            pbar = MagicMock()

            # Cancel the downloader
            downloader.cancel()
            assert downloader.cancelled is True

            result = await downloader._download_one(mock_session, semaphore, req, pbar, None)

            assert result is False
            mock_session.get.assert_not_called()


class TestTileDownloaderMain:
    def test_download_empty_requests(self):
        """Test that download handles empty request list gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def url_builder(z, x, y):
                return f"https://example.com/{z}/{x}/{y}.png"

            downloader = TileDownloader(output_dir, url_builder)

            # This should not raise an exception
            import asyncio

            asyncio.run(downloader.download([]))

    def test_download_integration_skip_existing(self):
        """Integration test for skipping existing files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def url_builder(z, x, y):
                return f"https://example.com/{z}/{x}/{y}.png"

            downloader = TileDownloader(output_dir, url_builder)

            # Create existing file
            tile_path = output_dir / "5" / "10" / "20.png"
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            tile_path.write_text("existing")

            # Mock the session to avoid actual HTTP calls
            with patch("aiohttp.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session

                requests = [TileRequest(5, 10, 20)]

                import asyncio

                asyncio.run(downloader.download(requests))

                # Should not have made any HTTP calls since file exists
                mock_session.get.assert_not_called()

    def test_control_methods(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def url_builder(z, x, y):
                return f"https://example.com/{z}/{x}/{y}.png"

            downloader = TileDownloader(output_dir, url_builder)

            # Test initial state
            assert not downloader.paused
            assert not downloader.cancelled

            # Test pause
            downloader.pause()
            assert downloader.paused
            assert not downloader.cancelled

            # Test resume
            downloader.resume()
            assert not downloader.paused
            assert not downloader.cancelled

            # Test cancel
            downloader.cancel()
            assert not downloader.paused
            assert downloader.cancelled
