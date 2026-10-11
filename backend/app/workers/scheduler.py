"""Fail-closed scheduler gate for collection workers.

This intentionally schedules no source until the allowlist has an approved
entry and LIVE_COLLECTION_ENABLED is explicitly true.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def enabled_sources() -> list[dict[str, object]]:
    path = Path(os.getenv("SOURCE_ALLOWLIST_FILE", "config/sources.allowlist.json"))
    if os.getenv("LIVE_COLLECTION_ENABLED", "false").lower() != "true" or not path.is_file():
        return []
    policy = json.loads(path.read_text())
    if not policy.get("live_collection_enabled"):
        return []
    return [source for source in policy.get("sources", []) if source.get("approved") and source.get("enabled")]


def main() -> None:
    while True:
        sources = enabled_sources()
        print(f"approved_sources={len(sources)} collection={'enabled' if sources else 'disabled'}", flush=True)
        # Source-specific plugins are dispatched here only after approval.
        time.sleep(300)


if __name__ == "__main__":
    main()
