import pytest

from aerospace_utils import ops


class TestMappings:
    def test_swap(self):
        assert ops.swap_mapping("1", "2") == {"1": "2", "2": "1"}

    def test_swap_rejects_same_workspace(self):
        with pytest.raises(ValueError):
            ops.swap_mapping("3", "3")

    def test_move(self):
        assert ops.move_mapping("4", "1") == {"4": "1"}

    def test_move_rejects_same_workspace(self):
        with pytest.raises(ValueError):
            ops.move_mapping("4", "4")

    def test_reorder_fills_sorted_slots_in_given_order(self):
        # Contents of 3 go to slot 1, contents of 1 to slot 2, contents of 2 to slot 3.
        assert ops.reorder_mapping(["3", "1", "2"]) == {"3": "1", "1": "2", "2": "3"}

    def test_reorder_skips_workspaces_that_keep_their_slot(self):
        assert ops.reorder_mapping(["1", "3", "2"]) == {"3": "2", "2": "3"}

    def test_reorder_sorts_slots_numerically(self):
        assert ops.reorder_mapping(["10", "9"]) == {"10": "9", "9": "10"}

    def test_reorder_needs_two_workspaces(self):
        with pytest.raises(ValueError):
            ops.reorder_mapping(["1"])

    def test_reorder_rejects_duplicates(self):
        with pytest.raises(ValueError):
            ops.reorder_mapping(["1", "2", "1"])


def test_natural_key_orders_numbers_before_names():
    names = ["S", "10", "2", "a", "1"]
    assert sorted(names, key=ops.natural_key) == ["1", "2", "10", "a", "S"]


def test_summarize_apps_counts_duplicates():
    windows = [
        ops.Window(1, "1", "Terminal", "a"),
        ops.Window(2, "1", "Browser", "b"),
        ops.Window(3, "1", "Terminal", "c"),
    ]
    assert ops.summarize_apps(windows) == "Terminal (2), Browser"


class TestRemap:
    def test_swap_exchanges_all_windows(self, fake, client):
        result = ops.remap(client, ops.swap_mapping("1", "2"))

        assert fake.windows_in("1") == [201, 202, 203]
        assert fake.windows_in("2") == [101]
        assert fake.windows_in("3") == [301]
        assert len(result.moves) == 4
        assert result.failures == []

    def test_move_merges_into_target(self, fake, client):
        ops.remap(client, ops.move_mapping("3", "1"))

        assert fake.windows_in("1") == [101, 301]
        assert fake.windows_in("3") == []

    def test_reorder_rotates_contents(self, fake, client):
        ops.remap(client, ops.reorder_mapping(["3", "1", "2"]))

        assert fake.windows_in("1") == [301]
        assert fake.windows_in("2") == [101]
        assert fake.windows_in("3") == [201, 202, 203]

    def test_swap_with_empty_workspace(self, fake, client):
        ops.remap(client, ops.swap_mapping("3", "4"))

        assert fake.windows_in("3") == []
        assert fake.windows_in("4") == [301]

    def test_dry_run_moves_nothing(self, fake, client):
        result = ops.remap(client, ops.swap_mapping("1", "2"), dry_run=True)

        assert len(result.moves) == 4
        assert fake.moves() == []
        assert fake.windows_in("1") == [101]

    def test_stays_on_focused_workspace_by_default(self, fake, client):
        ops.remap(client, ops.swap_mapping("1", "2"))

        assert fake.focused_workspace == "2"

    def test_follow_focuses_the_previously_focused_window(self, fake, client):
        ops.remap(client, ops.swap_mapping("1", "2"), follow=True)

        assert fake.focused_workspace == "1"
        assert fake.focused_window == 201

    def test_follow_without_focused_window_goes_to_target_workspace(self, fake, client):
        fake.focused_workspace = "3"
        fake.focused_window = None

        ops.remap(client, ops.move_mapping("3", "10"), follow=True)

        assert fake.focused_workspace == "10"
        assert not any(call[0] == "focus" for call in fake.calls)

    def test_failed_moves_are_reported_and_others_continue(self, fake, client):
        fake.broken_window_ids.add(202)

        result = ops.remap(client, ops.swap_mapping("1", "2"))

        assert [m.window.id for m, _ in result.failures] == [202]
        assert "202" in result.failures[0][1]
        assert fake.windows_in("1") == [201, 203]
        assert fake.windows_in("2") == [101, 202]
