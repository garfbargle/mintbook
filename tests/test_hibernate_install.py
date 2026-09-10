"""bin/hibernate-install --offset-from-filefrag.

resume_offset is the one value in the hibernation setup that fails silently.
A wrong device makes the resume not happen; a wrong offset makes the kernel
read whatever else lives at that block. So the parser gets its own tests.
"""
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / 'bin' / 'hibernate-install'


def offset(text):
    result = subprocess.run(
        [str(SCRIPT), '--offset-from-filefrag'],
        input=text, text=True, capture_output=True, check=True)
    return result.stdout.strip()


# Real output from this machine's /swapfile, 2026-09-10. The installer read
# 18980864 from it and wrote that to the command line.
REAL = """Filesystem type is: ef53
File size of /swapfile is 8589934592 (2097152 blocks of 4096 bytes)
 ext:     logical_offset:        physical_offset: length:   expected: flags:
   0:        0..   32767:   18980864..  19013631:  32768:
   1:    32768..   65535:   19013632..  19046399:  32768:
   2:    65536..   98303:   19046400..  19079167:  32768:
"""


class OffsetFromFilefrag(unittest.TestCase):

    def test_reads_first_extent_physical_start(self):
        self.assertEqual(offset(REAL), '18980864')

    def test_ignores_later_extents(self):
        # A fragmented swap file still resumes from its first block.
        self.assertEqual(offset(REAL).count('\n'), 0)

    def test_handles_a_single_extent_file(self):
        text = (" ext:     logical_offset:        physical_offset: length:"
                "   expected: flags:\n"
                "   0:        0.. 2097151:    4194304..   6291455:"
                " 2097152:             last,eof\n")
        self.assertEqual(offset(text), '4194304')

    def test_tight_columns_without_leading_space(self):
        # filefrag drops the padding once offsets get wide enough.
        text = "   0:        0..   32767:1234567..1267334:  32768:\n"
        self.assertEqual(offset(text), '1234567')

    def test_no_extent_line_yields_nothing(self):
        # The installer treats empty as fatal rather than defaulting to 0.
        self.assertEqual(offset("Filesystem type is: ef53\n"), '')

    def test_does_not_match_extent_ten_as_extent_zero(self):
        text = ("  10:    32768..   65535:   19013632..  19046399:  32768:\n"
                "   0:        0..   32767:   18980864..  19013631:  32768:\n")
        self.assertEqual(offset(text), '18980864')


if __name__ == '__main__':
    unittest.main()
