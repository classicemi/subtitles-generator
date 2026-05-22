from __future__ import annotations

import unittest

from app.models import SubtitleSegment
from app.subtitles import format_srt_timestamp, render_srt, render_vtt


class SubtitleFormattingTests(unittest.TestCase):
    def test_srt_timestamp_uses_milliseconds(self) -> None:
        self.assertEqual(format_srt_timestamp(3_723.456), "01:02:03,456")

    def test_render_srt_skips_empty_segments(self) -> None:
        output = render_srt(
            [
                SubtitleSegment(start=0, end=1.2, text="  Hello  world "),
                SubtitleSegment(start=1.3, end=2.0, text=" "),
            ]
        )
        self.assertEqual(output, "1\n00:00:00,000 --> 00:00:01,200\nHello world\n")

    def test_render_vtt_has_header(self) -> None:
        output = render_vtt([SubtitleSegment(start=0, end=1, text="Hello")])
        self.assertTrue(output.startswith("WEBVTT\n\n"))
        self.assertIn("00:00:00.000 --> 00:00:01.000", output)


if __name__ == "__main__":
    unittest.main()
