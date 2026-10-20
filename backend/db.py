"""طبقة التخزين — SQLite بملف واحد، كافية للنموذج الأولي وسهلة النقل إلى PostgreSQL لاحقًا."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    road TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    source TEXT NOT NULL,          -- JSON: نوع المصدر وعنوانه
    meta TEXT NOT NULL DEFAULT '{}',-- JSON: المرور، تاريخ الرصف، منطقة الطريق ROI...
    enabled INTEGER NOT NULL DEFAULT 1,
    region TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL REFERENCES cameras(id),
    ts TEXT NOT NULL,              -- ISO-8601 UTC
    kind TEXT NOT NULL,            -- weekly | sentinel | manual | seed
    image_path TEXT NOT NULL,
    annotated_path TEXT,
    condition_index REAL,
    crack_density REAL,
    pothole_count INTEGER,
    changed_pct REAL,
    quality TEXT,
    metrics TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_snap_cam_ts ON snapshots(camera_id, ts);
CREATE TABLE IF NOT EXISTS risk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL REFERENCES cameras(id),
    ts TEXT NOT NULL,
    score REAL NOT NULL,
    level TEXT NOT NULL,
    prob_90d REAL NOT NULL,
    weeks_to_threshold REAL,
    factors TEXT NOT NULL,
    forecast TEXT NOT NULL,
    recommendations TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_risk_cam_ts ON risk(camera_id, ts);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL REFERENCES cameras(id),
    ts TEXT NOT NULL,
    type TEXT NOT NULL,            -- sudden_change | new_pothole | risk_up | threshold | capture_failed | incident
    severity TEXT NOT NULL,        -- info | warning | critical
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    snapshot_id INTEGER,
    ack INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alert_ts ON alerts(ts);
CREATE TABLE IF NOT EXISTS maintenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL REFERENCES cameras(id),
    date TEXT NOT NULL,
    action TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS weather (
    region TEXT NOT NULL,
    date TEXT NOT NULL,
    tmax REAL NOT NULL,
    tmin REAL NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (region, date)
);
-- تتبّع كل عيب عبر الزمن (مطابقة المواقع بين اللقطات)
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL REFERENCES cameras(id),
    type TEXT NOT NULL,
    bbox TEXT NOT NULL,            -- JSON [x,y,w,h] آخر موضع
    first_ts TEXT NOT NULL,
    last_ts TEXT NOT NULL,
    hits INTEGER NOT NULL DEFAULT 1,
    misses INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,          -- tentative | confirmed | gone | repaired
    areas TEXT NOT NULL DEFAULT '[]', -- JSON [[ts, area], ...] لقياس نمو العيب
    confidence REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tracks_cam ON tracks(camera_id, status);
-- دورة حياة المشكلة: قبل (متوقعة) ← أثناء (نشطة) ← بعد (مُعالجة)
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL REFERENCES cameras(id),
    kind TEXT NOT NULL,            -- deterioration | pothole | cracking | sudden | obstruction
    stage TEXT NOT NULL,           -- predicted | active | resolved | monitoring | closed
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    predicted_ts TEXT,             -- متى توقّعها النظام
    expected_ts TEXT,              -- الموعد المتوقع لحدوثها
    detected_ts TEXT,              -- متى رُصدت فعلًا
    resolved_ts TEXT,              -- متى رُصد زوالها
    closed_ts TEXT,                -- انتهاء مراقبة ما بعد الإصلاح
    resolution TEXT,               -- repaired | cleared | not_occurred | recurred
    baseline_ci REAL,              -- مؤشر الحالة قبل المشكلة
    worst_ci REAL,
    last_ci REAL,
    track_ids TEXT NOT NULL DEFAULT '[]',
    events TEXT NOT NULL DEFAULT '[]'  -- JSON [{ts, stage, note}]
);
CREATE INDEX IF NOT EXISTS idx_issues_cam ON issues(camera_id, stage);
"""


def _migrate(c: sqlite3.Connection) -> None:
    """ترقية قواعد البيانات من الإصدارات السابقة."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(cameras)")}
    if "region" not in cols:
        c.execute("ALTER TABLE cameras ADD COLUMN region TEXT NOT NULL DEFAULT ''")
    wcols = {r[1] for r in c.execute("PRAGMA table_info(weather)")}
    if wcols and "region" not in wcols:  # ذاكرة طقس مؤقتة فقط — تُعاد بنيتها
        c.execute("DROP TABLE weather")
    c.commit()


def _connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = _connect()
            if _conn.execute("SELECT name FROM sqlite_master WHERE name='cameras'").fetchone():
                _migrate(_conn)
            _conn.executescript(SCHEMA)
        return _conn


def reset_connection() -> None:
    """للاختبارات: إغلاق الاتصال لإعادة فتحه على مسار جديد."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    with _lock:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


def one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def insert(table: str, row: dict[str, Any]) -> int:
    cols = list(row)
    vals = [json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in row.values()]
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    with tx() as c:
        return int(c.execute(sql, vals).lastrowid)


def loads(row: dict[str, Any] | None, *fields: str) -> dict[str, Any] | None:
    if row is None:
        return None
    for f in fields:
        if isinstance(row.get(f), str):
            row[f] = json.loads(row[f])
    return row
