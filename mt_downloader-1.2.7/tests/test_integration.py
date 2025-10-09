import os
import shutil
import sys
import tempfile
import subprocess
from pathlib import Path

# Get the path to the installed script
SCRIPT_PATH = shutil.which("map-tiles-downloader")
if SCRIPT_PATH is None:
    # Fallback: try to find it relative to the Python executable
    SCRIPT_PATH = os.path.join(os.path.dirname(sys.executable), "map-tiles-downloader")
    # On Windows, scripts might be in Scripts subdirectory
    if not os.path.exists(SCRIPT_PATH) and os.name == "nt":
        scripts_dir = os.path.join(os.path.dirname(sys.executable), "Scripts")
        SCRIPT_PATH = os.path.join(scripts_dir, "map-tiles-downloader.exe")

# Integration tests for end-to-end functionality
# These tests run the actual CLI commands and verify the results


class TestCLIIntegration:
    """Integration tests for CLI commands"""

    def test_bbox_command_dry_run(self):
        """Test bbox command with dry-run option"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Run bbox command with dry-run (use osm provider to avoid API key requirement)
            result = subprocess.run(
                [
                    SCRIPT_PATH,
                    "bbox",
                    "0",
                    "0",
                    "0.001",
                    "0.001",
                    "--provider",
                    "osm",
                    "--dry-run",
                    "--outdir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )

            assert result.returncode == 0
            assert "Planned tiles:" in (result.stdout + result.stderr)
            # Should not create any tile files
            assert not any(output_dir.rglob("*.png"))

    def test_bbox_command_with_provider(self):
        """Test bbox command with specific provider"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Run bbox command with OSM provider (no API key needed)
            result = subprocess.run(
                [
                    SCRIPT_PATH,
                    "bbox",
                    "0",
                    "0",
                    "0.001",
                    "0.001",
                    "--provider",
                    "osm",
                    "--dry-run",
                    "--outdir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )

            assert result.returncode == 0
            assert "Planned tiles:" in (result.stdout + result.stderr)

    def test_list_providers_command(self):
        """Test list providers command"""
        result = subprocess.run(
            [SCRIPT_PATH, "list", "providers"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        assert result.returncode == 0
        assert "thunderforest" in result.stdout
        assert "osm" in result.stdout
        assert "api_key_required" in result.stdout

    def test_list_regions_command(self):
        """Test list regions command"""
        result = subprocess.run(
            [SCRIPT_PATH, "list", "regions"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        assert result.returncode == 0
        assert "Europe" in result.stdout
        assert "North America" in result.stdout
        assert "United States" in result.stdout

    def test_invalid_command(self):
        """Test invalid command returns error"""
        result = subprocess.run(
            [SCRIPT_PATH, "invalid_command"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        assert result.returncode != 0
        assert "invalid choice" in result.stderr or "error:" in result.stderr

    def test_bbox_missing_coordinates(self):
        """Test bbox command with missing coordinates"""
        result = subprocess.run(
            [SCRIPT_PATH, "bbox"], capture_output=True, text=True, cwd=Path.cwd()
        )

        assert result.returncode != 0
        assert "error:" in result.stderr or "the following arguments are required:" in result.stderr

    def test_kml_command_missing_file(self):
        """Test kml command with missing file"""
        result = subprocess.run(
            [SCRIPT_PATH, "kml", "nonexistent.kml"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        assert result.returncode != 0
        assert "error:" in result.stderr or "No such file" in result.stderr


class TestKMLIntegration:
    """Integration tests for KML file processing"""

    def test_kml_command_with_valid_file(self):
        """Test KML command with a valid KML file"""
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

        with tempfile.TemporaryDirectory() as tmpdir:
            kml_file = Path(tmpdir) / "test.kml"
            kml_file.write_text(kml_content)
            output_dir = Path(tmpdir) / "output"

            result = subprocess.run(
                [
                    SCRIPT_PATH,
                    "kml",
                    str(kml_file),
                    "--provider",
                    "osm",
                    "--dry-run",
                    "--outdir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )

            assert result.returncode == 0
            assert "Planned tiles:" in (result.stdout + result.stderr)

    def test_kml_command_with_linestring(self):
        """Test KML command with LineString geometry"""
        kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Path</name>
      <LineString>
        <coordinates>
          -122.0,45.0,0
          -121.9,45.1,0
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>"""

        with tempfile.TemporaryDirectory() as tmpdir:
            kml_file = Path(tmpdir) / "test.kml"
            kml_file.write_text(kml_content)
            output_dir = Path(tmpdir) / "output"

            result = subprocess.run(
                [
                    SCRIPT_PATH,
                    "kml",
                    str(kml_file),
                    "--provider",
                    "osm",
                    "--dry-run",
                    "--outdir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )

            assert result.returncode == 0
            assert "Planned tiles:" in (result.stdout + result.stderr)
            # Should have created multiple regions from the linestring
            output_lines = result.stdout.strip().split("\n")
            tiles_line = [line for line in output_lines if "Planned tiles:" in line]
            assert tiles_line


class TestProviderIntegration:
    """Integration tests for provider functionality"""

    def test_thunderforest_provider_requires_api_key(self):
        """Test that Thunderforest provider requires API key"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = subprocess.run(
                [
                    SCRIPT_PATH,
                    "bbox",
                    "0",
                    "0",
                    "0.001",
                    "0.001",
                    "--provider",
                    "thunderforest",
                    "--dry-run",
                    "--outdir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )

            # Should fail because no API key provided
            assert result.returncode != 0
            # Check stderr for API key error message
            stderr_content = result.stderr.lower()
            assert (
                "api-key" in stderr_content
                or "api key" in stderr_content
                or "thunderforest" in stderr_content
            )

    def test_thunderforest_provider_with_api_key(self):
        """Test Thunderforest provider with API key"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Set fake API key environment variable
            env = os.environ.copy()
            env["THUNDERFOREST_API_KEY"] = "fake_key"

            result = subprocess.run(
                [
                    SCRIPT_PATH,
                    "bbox",
                    "0",
                    "0",
                    "0.001",
                    "0.001",
                    "--provider",
                    "thunderforest",
                    "--dry-run",
                    "--outdir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
                env=env,
            )

            assert result.returncode == 0
            assert "Planned tiles:" in (result.stdout + result.stderr)


class TestErrorHandlingIntegration:
    """Integration tests for error handling scenarios"""

    def test_invalid_zoom_levels(self):
        """Test handling of invalid zoom levels"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = subprocess.run(
                [
                    SCRIPT_PATH,
                    "bbox",
                    "0",
                    "0",
                    "0.001",
                    "0.001",
                    "--provider",
                    "osm",
                    "--max-zoom",
                    "25",  # Invalid zoom level
                    "--dry-run",
                    "--outdir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )

            # Should still work but might produce 0 tiles
            assert result.returncode == 0
            assert "Planned tiles:" in (result.stdout + result.stderr)

    def test_concurrency_parameter(self):
        """Test concurrency parameter handling"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = subprocess.run(
                [
                    SCRIPT_PATH,
                    "bbox",
                    "0",
                    "0",
                    "0.001",
                    "0.001",
                    "--provider",
                    "osm",
                    "--concurrency",
                    "1",
                    "--dry-run",
                    "--outdir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )

            assert result.returncode == 0
            assert "Planned tiles:" in (result.stdout + result.stderr)
