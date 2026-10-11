"""Print a verifiable, text-only inventory of the checked-in archive.

This deliberately does not alter the evidence database.  A reviewed migration
must map archive pages to the normalized source/persona/post schema first.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from collectors.archive_html import LocalArchiveIngestor
from backend.app.services.safety import evaluate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    arguments = parser.parse_args()
    ingestor = LocalArchiveIngestor(arguments.archive)
    seen = admitted = rejected = 0
    for document in ingestor.fetch():
        seen += 1
        decision = evaluate(document.content_type, document.text)
        if decision.admitted:
            admitted += 1
        else:
            rejected += 1
    print(f"source={ingestor.source_id} pages_seen={seen} text_admitted={admitted} rejected={rejected}")


if __name__ == "__main__":
    main()
