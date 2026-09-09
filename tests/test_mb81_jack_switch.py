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


if __name__ == "__main__":
    unittest.main()
