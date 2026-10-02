"""Strict media envelopes and deterministic rolling-caption assembly (milliseconds)."""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_MEDIA_MS = 7 * 24 * 60 * 60 * 1000


class Interval(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start_ms: int = Field(ge=0, le=MAX_MEDIA_MS, strict=True)
    end_ms: int = Field(gt=0, le=MAX_MEDIA_MS, strict=True)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must exceed start_ms")
        return self


class Caption(Interval):
    text: str = Field(min_length=1, max_length=12000)


def merge_intervals(intervals: Iterable[Interval]) -> list[list[int]]:
    result: list[list[int]] = []
    for item in sorted(intervals, key=lambda value: value.start_ms):
        if result and item.start_ms <= result[-1][1]:
            result[-1][1] = max(result[-1][1], item.end_ms)
        else:
            result.append([item.start_ms, item.end_ms])
    return result


def covered(start: int, end: int, intervals: list[list[int]]) -> bool:
    return any(left <= start and right >= end for left, right in intervals)


def watermark(intervals: list[list[int]]) -> int:
    return intervals[0][1] if intervals and intervals[0][0] == 0 else 0


def tokens(text: str) -> list[str]:
    # Deduplication must not erase case-sensitive identifiers or operators.
    return text.split()


def novel_suffix(previous: str, current: str) -> str:
    old, new = tokens(previous), tokens(current)
    if new and any(old[i:i + len(new)] == new for i in range(len(old) - len(new) + 1)):
        return ""
    for count in range(min(len(old), len(new)), 0, -1):
        if old[-count:] == new[:count]:
            return " ".join(current.split()[count:])
    return current.strip()


def temporal_chunks(captions: list[Caption]) -> tuple[list[dict], dict]:
    # One cue per chunk: stable incremental IDs, no invented word-level timing.
    # Only overlapping/adjacent cue windows can be rolling-caption duplicates.
    result, seen = [], set()
    previous: Caption | None = None
    raw_bytes = sum(len(c.text.encode()) for c in captions)
    for cue in sorted(captions, key=lambda c: (c.start_ms, c.end_ms, c.text)):
        identity = (cue.start_ms, cue.end_ms, cue.text)
        if identity in seen:
            continue
        seen.add(identity)
        text = " ".join(cue.text.split())
        if previous and cue.start_ms <= previous.end_ms:
            text = novel_suffix(previous.text, text)
        previous = cue
        if text:
            result.append({"start_ms": cue.start_ms, "end_ms": cue.end_ms, "text": text})
    return result, {
        "raw_caption_bytes": raw_bytes,
        "deduplicated_bytes": sum(len(c["text"].encode()) for c in result),
        "avoided_duplicate_chunks": len(captions) - len(result),
    }


def fingerprint(source: str, chunks: list[dict]) -> str:
    return hashlib.sha256(json.dumps([source, chunks], sort_keys=True).encode()).hexdigest()
