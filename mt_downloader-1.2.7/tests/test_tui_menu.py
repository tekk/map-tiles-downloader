from unittest.mock import Mock

# Test the hierarchical selection logic in the Menu class
# Since the Menu class requires curses stdscr, we'll test the logic indirectly


def test_hierarchical_menu_logic():
    """Test that hierarchical selection logic works correctly"""
    # Mock curses stdscr
    stdscr = Mock()
    stdscr.getmaxyx.return_value = (24, 80)
    stdscr.getch.return_value = ord("q")  # Quit immediately

    # Import after setting up mocks to avoid curses import issues
    from map_tiles_downloader.tui import Menu

    # Test choices that simulate the state selection menu
    choices = [
        "[All states/regions]",
        "Slovakia / All of Slovakia",
        "Slovakia / Bratislava",
        "Slovakia / Košice",
        "Czechia / All of Czechia",
        "Czechia / Prague",
        "Czechia / Brno",
    ]

    # Create menu with hierarchical selection
    menu = Menu(
        stdscr,
        "Test hierarchical menu",
        choices,
        multi=True,
        all_toggle=True,
        hierarchical_all=True,
        colors_enabled=True,
    )

    # Test the _get_display_selected method
    menu.selected = {1: False, 2: True, 3: True, 4: False, 5: True, 6: True}

    # "Slovakia / All of Slovakia" should be displayed as selected since both Bratislava and Košice are selected
    assert menu._get_display_selected(1)  # Slovakia / All of Slovakia

    # "Czechia / All of Czechia" should be displayed as selected since both Prague and Brno are selected
    assert menu._get_display_selected(4)  # Czechia / All of Czechia

    # Test with partial selection
    menu.selected = {1: False, 2: True, 3: False, 4: False, 5: True, 6: False}

    # "Slovakia / All of Slovakia" should not be displayed as selected since only Bratislava is selected
    assert not menu._get_display_selected(1)  # Slovakia / All of Slovakia

    # "Czechia / All of Czechia" should not be displayed as selected since only Prague is selected
    assert not menu._get_display_selected(4)  # Czechia / All of Czechia

    # Test with no selection
    menu.selected = {}

    assert not menu._get_display_selected(1)
    assert not menu._get_display_selected(4)


if __name__ == "__main__":
    test_hierarchical_menu_logic()
    print("All tests passed!")
