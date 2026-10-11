"""Interfaces shared by every lawful, read-only source collector."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class CollectedDocument:
    """Text-only content admitted to the extraction pipeline."""

    source_id: str
    locator: str
    collected_at: datetime
    text: str
    content_hash: str
    content_type: str = "text/html"


class BaseIngestor(ABC):
    """A plugin contract: no authentication, exploitation, or media collection."""

    source_id: str
    reliability: float

    @abstractmethod
    def fetch(self) -> Iterable[CollectedDocument]:
        """Yield public, text-only documents; implementations must be resumable."""

    @abstractmethod
    def parse(self, document: CollectedDocument) -> dict[str, object]:
        """Return normalized, source-attributed metadata for one document."""
