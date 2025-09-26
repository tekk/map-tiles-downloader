#!/usr/bin/env python3
"""Entry point for the map-tiles-downloader executable."""

import sys
import os

# Add the src directory to the path so we can import the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from map_tiles_downloader.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

