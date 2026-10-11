"""Admission controls for collection pipelines.

This module intentionally fails closed: media is never admitted and a source
can be blocklisted by a configured policy marker before persistence.
"""

from __future__ import annotations

from dataclasses import dataclass


MEDIA_TYPES = {"image/", "audio/", "video/", "application/pdf", "application/zip"}


@dataclass(frozen=True)
class SafetyDecision:
    admitted: bool
    reason: str
    block_source: bool = False


def evaluate(content_type: str, text: str, prohibited_markers: tuple[str, ...] = ()) -> SafetyDecision:
    normalized_type = content_type.lower()
    if any(normalized_type.startswith(prefix) for prefix in MEDIA_TYPES):
        return SafetyDecision(False, "media is outside the text-and-metadata policy")
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in prohibited_markers):
        return SafetyDecision(False, "configured prohibited-content marker detected", block_source=True)
    if not text.strip():
        return SafetyDecision(False, "empty text")
    return SafetyDecision(True, "text metadata admitted")
