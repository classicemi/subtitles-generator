from __future__ import annotations

import re

from app.models import SubtitleSegment


def format_srt_timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    return format_srt_timestamp(seconds).replace(",", ".")


def normalize_subtitle_text(text: str) -> str:
    compact = re.sub(r"[ \t]+", " ", text.strip())
    return re.sub(r"\n{3,}", "\n\n", compact)


def render_srt(segments: list[SubtitleSegment]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = normalize_subtitle_text(segment.text)
        if not text:
            continue
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(segment.start)} --> {format_srt_timestamp(segment.end)}",
                    text,
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def render_vtt(segments: list[SubtitleSegment]) -> str:
    blocks = ["WEBVTT", ""]
    for segment in segments:
        text = normalize_subtitle_text(segment.text)
        if not text:
            continue
        blocks.append(f"{format_vtt_timestamp(segment.start)} --> {format_vtt_timestamp(segment.end)}")
        blocks.append(text)
        blocks.append("")
    return "\n".join(blocks)
