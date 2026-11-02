from tools.relay_selftest import TWENTY_MB, describe_path, format_result


def test_route_is_chosen_by_size():
    assert describe_path(TWENTY_MB, True).startswith("bot client")
    assert describe_path(TWENTY_MB + 1, True).startswith("relay")
    assert describe_path(TWENTY_MB + 1, False).startswith("REJECTED")


def test_result_line_passes_within_tolerance_and_flags_mismatch():
    ok = format_result("a.mp4", 100_000_000, 100_000_000, 10.0, "relay")
    assert ok.startswith("PASS") and "9.5 MB/s" in ok
    assert format_result("a.mp4", 100_000_000, 99_000_000, 10.0, "relay").startswith("SIZE MISMATCH")
    assert format_result("a.mp4", 0, 5, 0.0, "x").startswith("SIZE MISMATCH")
