# Map Tiles Downloader

## For Meshtastic & MeshCore

This app helps you fetch map tiles quickly, for offline use. You can pick places using a simple text interface, choose tiles provider and map style, and then download the exact areas that you need. It shows download progress, speed, ETA, and estimates how much disk space will the maps use.

[![CI](https://github.com/tekk/map-tiles-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/tekk/map-tiles-downloader/actions/workflows/ci.yml)
[![Release](https://github.com/tekk/map-tiles-downloader/actions/workflows/release.yml/badge.svg)](https://github.com/tekk/map-tiles-downloader/actions/workflows/release.yml)
[![PyPI - Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)

[![asciicast](https://asciinema.org/a/747669.svg)](https://asciinema.org/a/747669)

## Install with pipx (recommended)

pipx installs Python apps into isolated environments and exposes the commands on your PATH.

#### macOS (Homebrew)

```bash
brew install pipx
pipx ensurepath # then restart your terminal
pipx install mt-downloader
mt-downloader  # or: map-tiles-downloader
```

#### Windows (winget)

In PowerShell:

```powershell
winget install --id=Python.Pipx -e
pipx ensurepath # then close and reopen the terminal
pipx install mt-downloader
mt-downloader  # or: map-tiles-downloader
```

## Pre-compiled binaries

Download the installer/pre-compiled binaries from the Github [Releases](https://github.com/tekk/map-tiles-downloader/releases) page.

## Source code

The source code lives in the GitHub repository: [tekk/map-tiles-downloader](https://github.com/tekk/map-tiles-downloader).

### If you want to compile yourself

First, install the project into a virtual environment. Then launch the interactive interface and follow the prompts. Select one or more continents, countries, and regions, choose a provider (Thunderforest or OpenStreetMap), set zoom levels, and pick an output directory. If the provider needs an API key you’ll be asked for it.

#### MacOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install . # note the dot at the end of command
mt-downloader
```

#### Windows

In Powershell in Windows Terminal (not cmd), run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r .\requirements.txt
pip install . # note the dot at the end of command
mt-downloader
```

If you need to automate, or prefer commands instead of the guided interface, there are `bbox` and `kml` subcommands (beta). Bounding box mode lets you fetch tiles for a given rectangle. KML mode expands points and routes into small areas around each location.

```bash
mt-downloader bbox SOUTH WEST NORTH EAST --max-zoom 12 -o ~/maps/out
```

```bash
mt-downloader kml /path/to/file.kml --max-zoom 12 -o ~/maps/out
```

For [Thunderforest](https://www.thunderforest.com/docs/apikeys/), set your API key once per session, or pass it with `-k`.

```bash
export THUNDERFOREST_API_KEY="your_key_here"
```

You can also preview a download without fetching data to see how many tiles you’ll get.

```bash
mt-downloader bbox 45.9668 5.7767 48.3068 8.7167 --max-zoom 12 --dry-run
```

That’s all you need. Launch the TUI, pick areas, and the downloader will handle the rest.

## Contributing

I'll be very happy for any kind of contributions. Feel free to fork and make a PR, or open an issue. I'll try to maintain this project as long as I'll have enough spare time to do so.

This project is created and maintained with :heart: by [tekk](https://github.com/tekk).
