from map_tiles_downloader.cli import build_parser


def test_cli_subcommands_exist():
    parser = build_parser()
    # Access argparse internal structure to inspect subcommand names
    subparsers_actions = [
        action for action in parser._subparsers._group_actions  # type: ignore[attr-defined]
    ]
    assert subparsers_actions, "No subparsers found on CLI parser"
    choices = set(subparsers_actions[0].choices.keys())  # type: ignore[attr-defined]
    expected = {"wizard", "bbox", "kml", "list", "tui"}
    missing = expected - choices
    assert not missing, f"Missing CLI subcommands: {missing}"


