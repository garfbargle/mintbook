import importlib.machinery
import importlib.util
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "bin" / "mb81-jack-switch"
LOADER = importlib.machinery.SourceFileLoader("mb81_jack_switch", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
MODULE = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MODULE)


class JackSwitchParsingTests(unittest.TestCase):
    def test_finds_headphone_control(self):
        controls = (
            "numid=4,iface=CARD,name='Headphone Jack'\n"
            "numid=5,iface=MIXER,name='Speaker Playback Switch'\n"
        )
        with mock.patch.object(MODULE, "capture", return_value=controls):
            self.assertEqual(MODULE.find_jack_control("0"), "4")

    def test_reads_jack_state(self):
        with mock.patch.object(
            MODULE, "capture", return_value="; type=BOOLEAN : values=on\n"
        ):
            self.assertEqual(MODULE.jack_state("0", "4"), "on")

    def test_maps_pipewire_node_names_to_ids(self):
        listing = """
        id 31, type PipeWire:Interface:Node/3
            object.serial = "31"
            node.name = "MacBook_Speaker_Raw"
        id 42, type PipeWire:Interface:Node/3
            node.name = "input.MacBook_Speaker"
        """
        with mock.patch.object(MODULE, "capture", return_value=listing):
            self.assertEqual(
                MODULE.pipewire_nodes(),
                {"MacBook_Speaker_Raw": "31", "input.MacBook_Speaker": "42"},
            )


class WaitForTests(unittest.TestCase):
    """Startup polling. Resume re-creates the card after this unit restarts."""

    def test_returns_first_value_without_sleeping(self):
        probe = mock.Mock(return_value="0")
        with mock.patch.object(MODULE.time, "sleep") as sleep:
            deadline = MODULE.time.monotonic() + 5
            self.assertEqual(MODULE.wait_for(probe, deadline), "0")
        probe.assert_called_once_with()
        sleep.assert_not_called()

    def test_retries_until_the_control_appears(self):
        probe = mock.Mock(side_effect=[None, None, "4"])
        with mock.patch.object(MODULE.time, "sleep") as sleep:
            deadline = MODULE.time.monotonic() + 5
            self.assertEqual(MODULE.wait_for(probe, deadline), "4")
        self.assertEqual(probe.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_gives_up_at_the_deadline(self):
        probe = mock.Mock(return_value=None)
        with mock.patch.object(MODULE.time, "sleep") as sleep:
            # Already expired: still probes once, then reports failure rather
            # than looping forever.
            self.assertIsNone(MODULE.wait_for(probe, MODULE.time.monotonic() - 1))
        probe.assert_called_once_with()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
