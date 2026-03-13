"""
database.py — supports both SQLite (local) and PostgreSQL (cloud)
If DATABASE_URL env var is set, uses PostgreSQL. Otherwise uses SQLite.
"""

import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
_USE_PG      = bool(DATABASE_URL)

# ── PostgreSQL helpers ────────────────────────────────────────────────────────

def _pg_conn():
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def _pg_exec(sql: str, params=(), fetch=False):
    import psycopg2.extras
    conn = _pg_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        result = cur.fetchall() if fetch else None
        conn.commit()
        return result or []
    except Exception as e:
        conn.rollback()
        logger.error("PG error: %s", e)
        return []
    finally:
        conn.close()


# ── SQLite helpers ────────────────────────────────────────────────────────────

_DB_PATH = os.path.join(os.path.dirname(__file__), "spf_monitor.db")


def _sq_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── init ──────────────────────────────────────────────────────────────────────

def init():
    if _USE_PG:
        _pg_exec("""
            CREATE TABLE IF NOT EXISTS posts (
                post_id    TEXT PRIMARY KEY,
                source     TEXT,
                url        TEXT,
                content    TEXT,
                author     TEXT,
                flagged    BOOLEAN DEFAULT FALSE,
                emailed    BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        _pg_exec("""
            CREATE TABLE IF NOT EXISTS feedback (
                id         SERIAL PRIMARY KEY,
                post_id    TEXT,
                decision   TEXT,
                reason     TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        _pg_exec("""
            CREATE TABLE IF NOT EXISTS learned_rules (
                id         SERIAL PRIMARY KEY,
                rule_type  TEXT,
                pattern    TEXT UNIQUE,
                reason     TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        logger.info("PostgreSQL tables ready")
    else:
        conn = _sq_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
                post_id    TEXT PRIMARY KEY,
                source     TEXT,
                url        TEXT,
                content    TEXT,
                author     TEXT,
                flagged    INTEGER DEFAULT 0,
                emailed    INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id    TEXT,
                decision   TEXT,
                reason     TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS learned_rules (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_type  TEXT,
                pattern    TEXT UNIQUE,
                reason     TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        conn.close()
        logger.info("SQLite tables ready")


# ── public API ────────────────────────────────────────────────────────────────

def seen(post_id: str) -> bool:
    if _USE_PG:
        rows = _pg_exec("SELECT 1 FROM posts WHERE post_id=%s", (post_id,), fetch=True)
        return bool(rows)
    conn = _sq_conn()
    row  = conn.execute("SELECT 1 FROM posts WHERE post_id=?", (post_id,)).fetchone()
    conn.close()
    return bool(row)


def save_post(post_id, source, url, content, author, flagged):
    if _USE_PG:
        _pg_exec("""
            INSERT INTO posts (post_id, source, url, content, author, flagged)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (post_id) DO NOTHING
        """, (post_id, source, url, content, author, flagged))
    else:
        conn = _sq_conn()
        conn.execute("""
            INSERT OR IGNORE INTO posts (post_id, source, url, content, author, flagged)
            VALUES (?,?,?,?,?,?)
        """, (post_id, source, url, content, author, int(flagged)))
        conn.commit()
        conn.close()


def mark_emailed(post_id: str):
    if _USE_PG:
        _pg_exec("UPDATE posts SET emailed=TRUE WHERE post_id=%s", (post_id,))
    else:
        conn = _sq_conn()
        conn.execute("UPDATE posts SET emailed=1 WHERE post_id=?", (post_id,))
        conn.commit()
        conn.close()


def save_feedback(post_id: str, decision: str, reason: str):
    if _USE_PG:
        _pg_exec(
            "INSERT INTO feedback (post_id, decision, reason) VALUES (%s,%s,%s)",
            (post_id, decision, reason)
        )
    else:
        conn = _sq_conn()
        conn.execute(
            "INSERT INTO feedback (post_id, decision, reason) VALUES (?,?,?)",
            (post_id, decision, reason)
        )
        conn.commit()
        conn.close()


def save_rule(rule_type: str, pattern: str, reason: str):
    if _USE_PG:
        _pg_exec("""
            INSERT INTO learned_rules (rule_type, pattern, reason)
            VALUES (%s,%s,%s)
            ON CONFLICT (pattern) DO NOTHING
        """, (rule_type, pattern, reason))
    else:
        conn = _sq_conn()
        conn.execute("""
            INSERT OR IGNORE INTO learned_rules (rule_type, pattern, reason)
            VALUES (?,?,?)
        """, (rule_type, pattern, reason))
        conn.commit()
        conn.close()


def get_rules() -> list:
    if _USE_PG:
        rows = _pg_exec("SELECT rule_type, pattern, reason FROM learned_rules", fetch=True)
        return [dict(r) for r in rows]
    conn  = _sq_conn()
    rows  = conn.execute("SELECT rule_type, pattern, reason FROM learned_rules").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def recent_incorrect_feedback(limit=10) -> list:
    if _USE_PG:
        rows = _pg_exec("""
            SELECT f.post_id, f.reason, p.content, p.source
            FROM feedback f LEFT JOIN posts p ON f.post_id=p.post_id
            WHERE f.decision='incorrect'
            ORDER BY f.created_at DESC LIMIT %s
        """, (limit,), fetch=True)
        return [dict(r) for r in rows]
    conn = _sq_conn()
    rows = conn.execute("""
        SELECT f.post_id, f.reason, p.content, p.source
        FROM feedback f LEFT JOIN posts p ON f.post_id=p.post_id
        WHERE f.decision='incorrect'
        ORDER BY f.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_flagged_posts(limit=50) -> list:
    """For dashboard — return recent flagged posts with feedback counts."""
    if _USE_PG:
        rows = _pg_exec("""
            SELECT p.*,
                COUNT(CASE WHEN f.decision='correct' THEN 1 END) as correct_count,
                COUNT(CASE WHEN f.decision='incorrect' THEN 1 END) as incorrect_count
            FROM posts p
            LEFT JOIN feedback f ON p.post_id=f.post_id
            WHERE p.flagged=TRUE
            GROUP BY p.post_id
            ORDER BY p.created_at DESC
            LIMIT %s
        """, (limit,), fetch=True)
        return [dict(r) for r in rows]
    conn = _sq_conn()
    rows = conn.execute("""
        SELECT p.*,
            COUNT(CASE WHEN f.decision='correct' THEN 1 END) as correct_count,
            COUNT(CASE WHEN f.decision='incorrect' THEN 1 END) as incorrect_count
        FROM posts p
        LEFT JOIN feedback f ON p.post_id=f.post_id
        WHERE p.flagged=1
        GROUP BY p.post_id
        ORDER BY p.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """For dashboard summary stats."""
    if _USE_PG:
        rows = _pg_exec("""
            SELECT
                COUNT(*) FILTER (WHERE flagged=TRUE) as flagged,
                COUNT(*) FILTER (WHERE flagged=FALSE) as scanned,
                COUNT(*) FILTER (WHERE source='instagram') as instagram,
                COUNT(*) FILTER (WHERE source IN ('straits_times','zaobao')) as news
            FROM posts
        """, fetch=True)
        r = dict(rows[0]) if rows else {}
        rules = _pg_exec("SELECT COUNT(*) as c FROM learned_rules", fetch=True)
        r["learned_rules"] = dict(rules[0])["c"] if rules else 0
        return r
    conn = _sq_conn()
    r    = dict(conn.execute("""
        SELECT
            COUNT(CASE WHEN flagged=1 THEN 1 END) as flagged,
            COUNT(CASE WHEN flagged=0 THEN 1 END) as scanned,
            COUNT(CASE WHEN source='instagram' THEN 1 END) as instagram,
            COUNT(CASE WHEN source IN ('straits_times','zaobao') THEN 1 END) as news
        FROM posts
    """).fetchone())
    r["learned_rules"] = conn.execute("SELECT COUNT(*) FROM learned_rules").fetchone()[0]
    conn.close()
    return r
