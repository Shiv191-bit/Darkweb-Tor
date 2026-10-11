"""Read-only analyst API over the locally ingested research dataset.

The service deliberately performs no live collection or active probing.  It is
the safe local query and export layer used by the DarkTrace dashboard.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "data" / "darktrace_normalized.db"
FRONTEND = ROOT / "frontend" / "dist"

app = FastAPI(title="DarkTrace Analyst API", version="0.1.0")


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def log_event(action: str, resource: str, parameters: dict[str, Any], count: int) -> None:
    """Append a hash-chained local audit event without retaining request bodies."""
    with database() as connection:
        previous = connection.execute(
            "SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous[0] if previous else "0" * 64
        timestamp = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        row_hash = hashlib.sha256(
            f"{previous_hash}|{timestamp}|{action}|{resource}|{payload}|{count}".encode()
        ).hexdigest()
        connection.execute(
            """INSERT INTO audit_log
               (timestamp, username, role, action, resource, query_parameters,
                result_count, ip_address, outcome, previous_hash, row_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, "local-analyst", "analyst", action, resource, payload,
             count, "local", "success", previous_hash, row_hash),
        )
        connection.commit()


@app.get("/api/v1/dashboard/stats")
def dashboard_stats() -> dict[str, int]:
    with database() as connection:
        counts = {
            name: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for name, table in {
                "actors": "actors", "identifiers": "identifiers",
                "attributions": "attributions",
            }.items()
        }
        counts["hidden_services"] = connection.execute("SELECT COUNT(DISTINCT onion_address) FROM hidden_services").fetchone()[0]
        counts["high_confidence_attributions"] = connection.execute(
            "SELECT COUNT(*) FROM attributions WHERE confidence_score >= 70"
        ).fetchone()[0]
    return counts


@app.get("/api/v1/dashboard/sources/health")
def source_health() -> dict[str, list[dict[str, Any]]]:
    with database() as connection:
        data = rows(connection.execute(
            """SELECT market AS name, COUNT(*) AS actors,
                      MAX(last_scan_date) AS last_scan_date,
                      MIN(source_reliability) AS reliability
                 FROM actors GROUP BY market ORDER BY actors DESC"""
        ))
    # These are archived datasets, not live Tor services.  The dashboard's
    # historical "onion_address" label is populated with the source key so it
    # never implies that a live endpoint was contacted.
    return {"sources": [
        {
            "id": item["name"], "onion_address": item["name"],
            "is_live": False, "uptime_history": 0,
            "reliability_score": item["reliability"] or "unknown",
            "last_scan_date": item["last_scan_date"], "actor_count": item["actors"],
        }
        for item in data
    ]}


@app.get("/api/v1/actors")
def list_actors(
    request: Request,
    q: str | None = Query(default=None, max_length=128),
    market: str | None = None,
    category: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    clauses, values = [], []
    if q:
        clauses.append("(a.name LIKE ? OR a.description LIKE ?)")
        values.extend([f"%{q}%", f"%{q}%"])
    if market:
        clauses.append("a.market = ?")
        values.append(market)
    if category:
        clauses.append("a.primary_category = ?")
        values.append(category)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with database() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM actors a {where}", values).fetchone()[0]
        result = rows(connection.execute(
            f"""SELECT a.*, COUNT(i.id) AS identifier_count
                  FROM actors a LEFT JOIN identifiers i ON i.actor_id = a.id
                  {where} GROUP BY a.id ORDER BY a.last_scan_date DESC, a.name
                  LIMIT ? OFFSET ?""", [*values, limit, offset]
        ))
    log_event("search", "actors", {"q": q, "market": market, "category": category}, len(result))
    return {"total": total, "items": result}


@app.get("/api/v1/actors/{actor_id}")
def actor_detail(actor_id: int) -> dict[str, Any]:
    with database() as connection:
        actor = connection.execute("SELECT * FROM actors WHERE id = ?", (actor_id,)).fetchone()
        if not actor:
            raise HTTPException(404, "Actor not found")
        identifiers = rows(connection.execute(
            "SELECT id, type, value, market FROM identifiers WHERE actor_id = ? ORDER BY type, value", (actor_id,)
        ))
        links = rows(connection.execute(
            """SELECT a.id, a.name, at.confidence_score, at.confidence_band, at.explanation, at.signals
                 FROM attributions at JOIN actors a ON a.id = at.target_actor_id
                 WHERE at.actor_id = ? AND at.target_actor_id IS NOT NULL
                 ORDER BY at.confidence_score DESC LIMIT 100""", (actor_id,)
        ))
        infrastructure = rows(connection.execute(
            "SELECT onion_address, indicator_type, indicator_value FROM hidden_services WHERE actor_id = ?", (actor_id,)
        ))
    log_event("view", f"actors/{actor_id}", {}, 1)
    return {"actor": dict(actor), "identifiers": identifiers, "persona_links": links,
            "infrastructure": infrastructure,
            "disclaimer": "Investigative lead, not proof."}


@app.get("/api/v1/graph/actor/{actor_id}")
def actor_graph(actor_id: int, minimum_confidence: float = Query(default=50, ge=0, le=100)) -> dict[str, Any]:
    with database() as connection:
        actor = connection.execute("SELECT id, name FROM actors WHERE id = ?", (actor_id,)).fetchone()
        if not actor:
            raise HTTPException(404, "Actor not found")
        related = rows(connection.execute(
            """SELECT target_actor_id AS id, confidence_score, confidence_band, explanation
                 FROM attributions WHERE actor_id = ? AND target_actor_id IS NOT NULL
                   AND confidence_score >= ? ORDER BY confidence_score DESC LIMIT 150""",
            (actor_id, minimum_confidence),
        ))
        ids = [item["id"] for item in related]
        names = {}
        if ids:
            marks = ",".join("?" for _ in ids)
            names = {row["id"]: row["name"] for row in connection.execute(
                f"SELECT id, name FROM actors WHERE id IN ({marks})", ids
            )}
    nodes = [{"data": {"id": str(actor["id"]), "label": actor["name"], "kind": "actor"}}]
    edges = []
    for item in related:
        nodes.append({"data": {"id": str(item["id"]), "label": names.get(item["id"], str(item["id"])), "kind": "actor"}})
        edges.append({"data": {"id": f"{actor_id}-{item['id']}", "source": str(actor_id), "target": str(item["id"]),
                                "confidence": item["confidence_score"], "evidence": item["explanation"]}})
    return {"nodes": nodes, "edges": edges, "disclaimer": "Investigative lead, not proof."}


@app.get("/api/v1/exports/actors.{format}")
def export_actors(format: str, q: str | None = None) -> Response:
    if format not in {"json", "csv"}:
        raise HTTPException(404, "Only JSON and CSV exports are available in the local build")
    with database() as connection:
        statement = "SELECT id, name, market, primary_category, last_scan_date, source, source_reliability FROM actors"
        values: list[str] = []
        if q:
            statement += " WHERE name LIKE ? OR description LIKE ?"
            values = [f"%{q}%", f"%{q}%"]
        data = rows(connection.execute(statement + " ORDER BY id", values))
    log_event("export", f"actors.{format}", {"q": q}, len(data))
    if format == "json":
        return JSONResponse({"disclaimer": "Investigative lead, not proof.", "records": data}, headers={"Content-Disposition": "attachment; filename=actors.json"})
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys() if data else ["id", "name"])
    writer.writeheader(); writer.writerows(data)
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=actors.csv"})


@app.get("/api/v1/actors/{actor_id}/report.pdf")
def actor_report(actor_id: int) -> Response:
    """Generate a local PDF case report from the stored evidence only."""
    with database() as connection:
        actor = connection.execute("SELECT * FROM actors WHERE id = ?", (actor_id,)).fetchone()
        if not actor:
            raise HTTPException(404, "Actor not found")
        identifiers = rows(connection.execute(
            "SELECT type, value, market FROM identifiers WHERE actor_id = ? ORDER BY type, value LIMIT 250", (actor_id,)
        ))
        attributions = rows(connection.execute(
            """SELECT alias, confidence_score, confidence_band, explanation
                 FROM attributions WHERE actor_id = ? ORDER BY confidence_score DESC LIMIT 100""", (actor_id,)
        ))
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=letter, title=f"DarkTrace actor {actor_id}")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("DarkTrace local research case report", styles["Title"]),
        Paragraph("Investigative lead, not proof. This report is derived solely from the local archived research dataset.", styles["BodyText"]),
        Spacer(1, 12),
        Paragraph(f"Actor profile: {actor['name']}", styles["Heading2"]),
        Paragraph(f"Market: {actor['market'] or 'unknown'}<br/>Category: {actor['primary_category'] or 'unclassified'}<br/>Last scan: {actor['last_scan_date'] or 'unknown'}<br/>Source: {actor['source'] or 'unknown'}", styles["BodyText"]),
        Spacer(1, 12),
        Paragraph("Identifiers", styles["Heading2"]),
    ]
    identifier_rows = [["Type", "Value", "Market"]] + [[item["type"], item["value"], item["market"] or ""] for item in identifiers]
    identifier_table = Table(identifier_rows, repeatRows=1, colWidths=[95, 330, 100])
    identifier_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#40205d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    story.extend([identifier_table, Spacer(1, 12), Paragraph("Attribution evidence", styles["Heading2"])])
    if attributions:
        for item in attributions:
            story.append(Paragraph(
                f"{item['confidence_band']} {item['confidence_score']}/100 — {item['alias'] or 'Unlabelled link'}: {item['explanation']}",
                styles["BodyText"],
            ))
    else:
        story.append(Paragraph("No attribution records are stored for this actor.", styles["BodyText"]))
    document.build(story)
    log_event("export", f"actors/{actor_id}/report.pdf", {}, 1)
    return Response(output.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=darktrace-actor-{actor_id}.pdf"})


@app.get("/api/v1/audit/verify")
def verify_audit_chain() -> dict[str, Any]:
    with database() as connection:
        entries = rows(connection.execute("SELECT * FROM audit_log ORDER BY id"))
    valid = all((not index or entry["previous_hash"] == entries[index - 1]["row_hash"]) for index, entry in enumerate(entries))
    return {"entries": len(entries), "chain_valid": valid}


app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str) -> Response:
    candidate = FRONTEND / path
    if path and candidate.is_file():
        media_types = {".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml"}
        return Response(candidate.read_bytes(), media_type=media_types.get(candidate.suffix, "application/octet-stream"))
    return Response((FRONTEND / "index.html").read_bytes(), media_type="text/html")
