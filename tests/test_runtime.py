from custom_components.vegga.runtime import active_sector_numbers, sector_is_irrigating


def test_active_sector_is_matched_exactly() -> None:
    rows = [
        {"sector": 1, "xProgramN": 2},
        {"sector": 2, "active": False},
    ]

    sectors = [
        {"_agronic_number": 1, "id": 119, "name": "Sector 1"},
        {"_agronic_number": 2, "id": 120, "name": "Sector 2"},
    ]

    assert sector_is_irrigating(rows, sectors, 1) is True
    assert sector_is_irrigating(rows, sectors, 2) is False


def test_adjacent_sector_is_not_a_match() -> None:
    rows = [{"sector": 1, "active": True}]

    sectors = [{"_agronic_number": 1}, {"_agronic_number": 2}]

    assert sector_is_irrigating(rows, sectors, 2) is False


def test_position_is_used_when_runtime_row_has_no_number() -> None:
    rows = [{"active": False}, {"running": True}]

    sectors = [{"name": "Uno"}, {"name": "Dos"}]

    assert sector_is_irrigating(rows, sectors, 1) is False
    assert sector_is_irrigating(rows, sectors, 2) is True


def test_empty_runtime_means_no_irrigation() -> None:
    assert sector_is_irrigating([], [{"_agronic_number": 19}], 19) is False


def test_database_id_is_resolved_to_controller_number() -> None:
    sectors = [
        {"_agronic_number": 1, "id": 30, "name": "Frutales"},
        {"_agronic_number": 2, "id": 81, "name": "Olivos"},
    ]
    runtime = [{"pk": {"id": 81}, "xProgramN": 5}]

    assert active_sector_numbers(runtime, sectors) == {2}


def test_a5500_irrigation_flag_marks_sector_active() -> None:
    sectors = [
        {"_agronic_number": 1, "pk": {"id": 30}, "name": "Frutales"},
        {"_agronic_number": 2, "pk": {"id": 81}, "name": "Olivos"},
    ]
    runtime = [
        {"pk": {"id": 30}, "irrigation": False, "xProgramN": 0},
        {"pk": {"id": 81}, "irrigation": True, "xProgramN": 0},
    ]

    assert active_sector_numbers(runtime, sectors) == {2}


def test_a5500_xstatus_matches_official_frontend_rule() -> None:
    sectors = [
        {"_agronic_number": number, "pk": {"id": number}}
        for number in range(1, 8)
    ]
    runtime = [
        {"pk": {"id": 1}, "xStatus": 0},
        {"pk": {"id": 2}, "xStatus": 1},
        {"pk": {"id": 3}, "xStatus": 2},
        {"pk": {"id": 4}, "xStatus": 3},
        {"pk": {"id": 5}, "xStatus": 4},
        {"pk": {"id": 6}, "xStatus": 5},
        {"pk": {"id": 7}, "xStatus": 6},
    ]

    assert active_sector_numbers(runtime, sectors) == {2, 3, 5}


def test_irrigation_true_response_is_not_treated_as_all_active() -> None:
    sectors = [
        {"_agronic_number": 1, "pk": {"id": 1}},
        {"_agronic_number": 2, "pk": {"id": 2}},
    ]
    runtime = [
        {"pk": {"id": 1}, "xStatus": 0},
        {"pk": {"id": 2}, "xStatus": 3},
    ]

    assert active_sector_numbers(runtime, sectors) == set()
