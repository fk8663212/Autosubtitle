from __future__ import annotations

import unittest

from autosubtitle.srt import SubtitleSegment, build_srt, format_timestamp


class SrtTest(unittest.TestCase):
    def test_timestamp_rounding(self) -> None:
        self.assertEqual(format_timestamp(3661.2346), "01:01:01,235")

    def test_empty_segments_do_not_break_numbering(self) -> None:
        result = build_srt(
            [
                SubtitleSegment(0, 1, ""),
                SubtitleSegment(1, 2, "Hello"),
            ]
        )
        self.assertTrue(result.startswith("1\n"))


if __name__ == "__main__":
    unittest.main()
