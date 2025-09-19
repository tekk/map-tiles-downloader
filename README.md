Map Tiles Downloader helps you fetch map tiles for offline use. You can pick places using a simple text interface, choose a tiles provider, and download exactly the areas you need. It shows progress, speed, ETA, and estimates how much disk space the download will take.

The source code lives in the GitHub repository: [tekk/map-tiles-downloader](https://github.com/tekk/map-tiles-downloader).

```bash
git clone https://github.com/tekk/map-tiles-downloader.git
cd map-tiles-downloader
```

To get started, install the project into a virtual environment. Then run the text-based installer and follow the prompts. You can select one or more continents, countries, and regions, choose a provider (Thunderforest or OpenStreetMap), set zoom levels, and choose where to save the tiles. If the provider needs an API key, you’ll be asked for it.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
mtd tui
```

[![asciicast](https://asciinema.org/a/9xSAZNvP6PCDkvBfKqDlJtnVv.svg)](https://asciinema.org/a/9xSAZNvP6PCDkvBfKqDlJtnVv)

If you prefer commands instead of the guided interface, you can use direct subcommands. Bounding box mode lets you fetch tiles for a given rectangle. KML mode expands points and routes into small areas around each location.

```bash
mtd bbox SOUTH WEST NORTH EAST --min-zoom 3 --max-zoom 12 -o ~/maps/out
```

```bash
mtd kml /path/to/file.kml --min-zoom 3 --max-zoom 12 -o ~/maps/out
```

For Thunderforest, set your API key once per session, or pass it with -k.

```bash
export THUNDERFOREST_API_KEY="your_key_here"
```

You can also preview a download without fetching data to see how many tiles you’ll get.

```bash
mtd bbox 45.9668 5.7767 48.3068 8.7167 --min-zoom 3 --max-zoom 12 --dry-run
```

That’s all you need. Launch the TUI, pick areas, and the downloader will handle the rest.

This project is created and maintained by [tekk](https://github.com/tekk).
