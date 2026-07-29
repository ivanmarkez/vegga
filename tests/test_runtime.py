from custom_components.vegga.runtime import sector_is_irrigating


def test_active_sector_is_matched_exactly() -> None:
    rows = [
        {"sector": 19, "xProgramN": 2},
        {"sector": 20, "active": False},
    ]

    assert sector_is_irrigating(rows, 19) is True
    assert sector_is_irrigating(rows, 20) is False


def test_adjacent_sector_is_not_a_match() -> None:
    rows = [{"sector": 1, "active": True}]

    assert sector_is_irrigating(rows, 2) is False


def test_position_is_used_when_runtime_row_has_no_number() -> None:
    rows = [{"active": False}, {"running": True}]

    assert sector_is_irrigating(rows, 1) is False
    assert sector_is_irrigating(rows, 2) is True


def test_empty_runtime_means_no_irrigation() -> None:
    assert sector_is_irrigating([], 19) is False
