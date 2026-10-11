"""Passive reader for a locally held HTML archive.

It deliberately has no network client.  This makes it appropriate for the
currently available archived dataset and keeps live collection opt-in.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from .base import BaseIngestor, CollectedDocument


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "img", "video", "audio", "source", "object", "embed"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "img", "video", "audio", "source", "object", "embed"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


class LocalArchiveIngestor(BaseIngestor):
    source_id = "local-archive"
    reliability = 0.85

    def __init__(self, archive_root: Path) -> None:
        self.archive_root = archive_root.resolve()

    def fetch(self) -> Iterable[CollectedDocument]:
        for file_path in self.archive_root.rglob("*.html"):
            raw = file_path.read_bytes()
            parser = _TextOnly()
            parser.feed(raw.decode("utf-8", errors="replace"))
            text = " ".join(" ".join(parser.parts).split())
            if not text:
                continue
            yield CollectedDocument(
                source_id=self.source_id,
                locator=str(file_path.relative_to(self.archive_root)),
                collected_at=datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc),
                text=text,
                content_hash=hashlib.sha256(raw).hexdigest(),
            )

    def parse(self, document: CollectedDocument) -> dict[str, object]:
        return {
            "source_id": document.source_id,
            "locator": document.locator,
            "collected_at": document.collected_at.isoformat(),
            "content_hash": document.content_hash,
            "text_length": len(document.text),
        }
