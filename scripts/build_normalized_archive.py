"""Build a clean, evidence-preserving SQLite database from the local archive.

Only observed source data is written.  It intentionally creates no attribution
or suspect-entity claims because one historical marketplace cannot substantiate
cross-market or real-world identity assertions on its own.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


class MarketPage(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.onions: set[str] = set()
        self.sellers: set[str] = set()
        self.listings: list[tuple[str, str | None]] = []
        self._active_listing: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "title": self._in_title = True
        if tag == "a":
            self._anchor_href = attributes.get("href")
            self._anchor_text = []
        for value in attributes.values():
            if value:
                self.onions.update(re.findall(r"\b[a-z2-7]{16,56}\.onion\b", value.lower()))

    def handle_data(self, data: str) -> None:
        if self._in_title: self.title += data
        if self._anchor_href is not None: self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title": self._in_title = False
        if tag != "a" or self._anchor_href is None: return
        href, text = self._anchor_href, " ".join("".join(self._anchor_text).split())
        if "/silkroad/item/" in href and text:
            self._active_listing = text
            self.listings.append((text, None))
        elif "/silkroad/user/" in href and text:
            handle = re.sub(r"\(\d+\)$", "", text).strip()
            # Marketplace UI labels are not users; only a concrete linked handle is kept.
            if handle and handle.lower() not in {"archivator", "messages", "settings", "log out"}:
                self.sellers.add(handle)
                if self._active_listing:
                    self.listings[-1] = (self._active_listing, handle)
                    self._active_listing = None
        self._anchor_href = None
        self._anchor_text = []


SCHEMA = """
CREATE TABLE sources (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, source_type TEXT NOT NULL, locator TEXT, reliability REAL NOT NULL, status TEXT NOT NULL, last_scan_date TEXT, blocklisted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE scan_runs (id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL, started_at TEXT NOT NULL, ended_at TEXT, pages_seen INTEGER NOT NULL DEFAULT 0, records_written INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(source_id) REFERENCES sources(id));
CREATE TABLE actors (id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, market TEXT, primary_category TEXT, last_scan_date TEXT, source TEXT, source_reliability TEXT, UNIQUE(name, market));
CREATE TABLE identifiers (id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL, type TEXT NOT NULL, value TEXT NOT NULL, market TEXT, first_seen TEXT, last_seen TEXT, source_locator TEXT, UNIQUE(actor_id, type, value), FOREIGN KEY(actor_id) REFERENCES actors(id));
CREATE TABLE listings (id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL, actor_id INTEGER, title TEXT NOT NULL, category TEXT, observed_at TEXT, source_locator TEXT NOT NULL, content_hash TEXT NOT NULL, FOREIGN KEY(source_id) REFERENCES sources(id), FOREIGN KEY(actor_id) REFERENCES actors(id));
CREATE TABLE hidden_services (id INTEGER PRIMARY KEY, actor_id INTEGER, onion_address TEXT NOT NULL, indicator_type TEXT NOT NULL, indicator_value TEXT NOT NULL, source_locator TEXT NOT NULL, UNIQUE(onion_address, indicator_type, indicator_value, source_locator));
CREATE TABLE evidence_signals (id INTEGER PRIMARY KEY, signal_type TEXT NOT NULL, family TEXT NOT NULL, actor_id INTEGER NOT NULL, target_actor_id INTEGER, suspect_entity_id INTEGER, raw_value TEXT, score REAL NOT NULL, source_id TEXT, source_reliability TEXT, observed_at TEXT, explanation TEXT NOT NULL);
CREATE TABLE attributions (id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL, target_actor_id INTEGER, suspect_entity_id INTEGER, alias TEXT, confidence_score REAL NOT NULL, confidence_band TEXT NOT NULL, explanation TEXT NOT NULL, signals TEXT, feedback TEXT, created_at TEXT);
CREATE TABLE suspect_entities (id INTEGER PRIMARY KEY, entity_type TEXT NOT NULL, name TEXT NOT NULL, details TEXT, source TEXT, evidence TEXT);
CREATE TABLE actor_entity_links (id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL, entity_id INTEGER NOT NULL, confidence_score REAL NOT NULL, evidence TEXT);
CREATE TABLE audit_log (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, username TEXT, role TEXT, action TEXT NOT NULL, resource TEXT, query_parameters TEXT, result_count INTEGER, ip_address TEXT, outcome TEXT NOT NULL, previous_hash TEXT, row_hash TEXT NOT NULL);
"""


def category_for(path: Path) -> str:
    values = {part.lower() for part in path.parts}
    categories = {"cannabis", "opioids", "opiods", "benzos", "ecstasy", "psychedelics", "stimulants", "dissociatives"}
    return "drugs" if values & categories else "other"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("database", type=Path)
    arguments = parser.parse_args()
    root, database = arguments.archive.resolve(), arguments.database.resolve()
    if database.exists(): database.unlink()
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA)
    now = datetime.now(timezone.utc).isoformat()
    source_id = connection.execute("INSERT INTO sources(name, source_type, locator, reliability, status, last_scan_date) VALUES (?, ?, ?, ?, ?, ?)", ("Silk Road historical archive", "archive", str(root), 0.85, "archived", now)).lastrowid
    scan_id = connection.execute("INSERT INTO scan_runs(source_id, started_at) VALUES (?, ?)", (source_id, now)).lastrowid
    actor_ids: dict[str, int] = {}
    pages = records = 0
    for path in root.rglob("*.html"):
        raw = path.read_bytes(); page = MarketPage(); page.feed(raw.decode("utf-8", errors="replace"))
        if not page.sellers and not page.onions: continue
        pages += 1; locator = str(path.relative_to(root)); observed = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(); category = category_for(path)
        for onion in page.onions:
            connection.execute("INSERT OR IGNORE INTO hidden_services(onion_address, indicator_type, indicator_value, source_locator) VALUES (?, ?, ?, ?)", (onion, "archived_url_observation", onion, locator))
        for seller in page.sellers:
            actor_id = actor_ids.get(seller)
            if actor_id is None:
                actor_id = connection.execute("INSERT INTO actors(name, market, primary_category, last_scan_date, source, source_reliability) VALUES (?, ?, ?, ?, ?, ?)", (seller, "silkroad1-2011", category, observed, "Silk Road historical archive", "high")).lastrowid
                actor_ids[seller] = actor_id
                connection.execute("INSERT INTO identifiers(actor_id, type, value, market, first_seen, last_seen, source_locator) VALUES (?, ?, ?, ?, ?, ?, ?)", (actor_id, "handle", seller, "silkroad1-2011", observed, observed, locator))
                records += 1
        for title, seller in page.listings:
            actor_id = actor_ids.get(seller) if seller else None
            connection.execute("INSERT INTO listings(source_id, actor_id, title, category, observed_at, source_locator, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?)", (source_id, actor_id, title, category, observed, locator, hashlib.sha256(raw).hexdigest()))
            records += 1
    connection.execute("UPDATE scan_runs SET ended_at=?, pages_seen=?, records_written=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), pages, records, scan_id))
    connection.commit()
    print(f"database={database} pages={pages} actors={len(actor_ids)} records={records}")


if __name__ == "__main__": main()
