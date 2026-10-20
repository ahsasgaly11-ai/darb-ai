"""خادم دَرْب AI — واجهة برمجية REST + الواجهة الرسومية الثابتة.

التشغيل:  uvicorn backend.app:app --host 0.0.0.0 --port 8000   (من مجلد darb-ai)
"""
from __future__ import annotations

import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, config, db, incidents, lifecycle, pipeline, scheduler, sources, vision

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("darb.app")

ADMIN_TOKEN = os.getenv("DARB_ADMIN_TOKEN", "")
state = {"seeding": False, "seeded": 0, "started_at": datetime.now(timezone.utc).isoformat()}


def _seed():
    state["seeding"] = True
    try:
        state["seeded"] = pipeline.seed_history()
        state["caught_up"] = pipeline.catch_up()
    except Exception:
        log.exception("seeding failed")
    finally:
        state["seeding"] = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_dirs()
    pipeline.sync_cameras()
    threading.Thread(target=_seed, daemon=True).start()
    if config.ENABLE_SCHEDULER:
        scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="DARB AI — دَرْب", version="1.0", lifespan=lifespan)


def admin(x_admin_token: str = Header(default="")):
    """العمليات المعدِّلة محمية برمز اختياري (DARB_ADMIN_TOKEN) — موصى به عند النشر العام."""
    if ADMIN_TOKEN and x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "رمز المشرف غير صحيح")


def _live(src: dict) -> dict | None:
    """مصدر البث المباشر الذي يعرضه المتصفح مباشرة من الجهة المالكة (دون المرور بالخادم)."""
    t = src.get("type")
    if t == "datagovsg":
        return {"kind": "datagovsg", "camera_id": str(src["camera_id"]), "refresh": 60}
    if t in sources.BASE_511:
        return {"kind": "image", "url": sources.cctv_url(src), "refresh": 30}
    if t == "caltrans":
        return {"kind": "hls", "url": src["url"], "refresh": 0}
    # الروابط المضافة يدويًا قد تحمل رموز دخول: لا تُكشف إلا إذا صرّح بها الإعداد ("live": true)
    if t == "hls" and src.get("live") and str(src.get("url", "")).startswith("https://"):
        return {"kind": "hls", "url": src["url"], "refresh": 0}
    if t in ("snapshot", "mjpeg") and src.get("live") and str(src.get("url", "")).startswith("https://"):
        return {"kind": "mjpeg" if t == "mjpeg" else "image", "url": src["url"], "refresh": 30}
    return None


def _camera_summary(cam: dict) -> dict:
    last = db.one("""SELECT id,ts,kind,condition_index,pothole_count,crack_density,changed_pct
                     FROM snapshots WHERE camera_id=? AND condition_index IS NOT NULL ORDER BY ts DESC LIMIT 1""", (cam["id"],))
    r = pipeline.latest_risk(cam["id"])
    open_alerts = db.one("SELECT COUNT(*) n FROM alerts WHERE camera_id=? AND ack=0", (cam["id"],))["n"]
    return {
        "id": cam["id"], "name": cam["name"], "road": cam["road"], "lat": cam["lat"], "lng": cam["lng"],
        "region": cam.get("region", ""),
        "open_issues": db.one("SELECT COUNT(*) n FROM issues WHERE camera_id=? AND stage IN ('predicted','active')", (cam["id"],))["n"],
        "source_type": cam["source"].get("type"), "live": _live(cam["source"]), "meta": cam["meta"], "enabled": bool(cam["enabled"]),
        "last_snapshot": last, "open_alerts": open_alerts,
        "risk": r and {"score": r["score"], "level": r["level"], "level_ar": r["forecast"].get("level_ar"),
                       "prob_90d": r["prob_90d"], "weeks_to_threshold": r["weeks_to_threshold"],
                       "priority": r["forecast"].get("priority"), "top_factor": r["factors"][0]["label"] if r["factors"] else None,
                       "slope": r["forecast"].get("ci_slope"), "ci": r["forecast"].get("ci")},
    }


@app.get("/api/status")
def status():
    return {**state, "jobs": scheduler.jobs(), "engine": vision.engine_name(), "ai_models": ai.names(),
            "incidents_enabled": incidents.enabled(), "weather": config.WEATHER_ENABLED,
            "schedule": {"weekly": f"{config.WEEKLY_DAY} {config.WEEKLY_HOUR:02d}:00 (التوقيت المحلي لكل منطقة)",
                         "sentinel_hours": config.SENTINEL_HOURS},
            "maintenance_threshold": config.MAINTENANCE_THRESHOLD,
            "regions": [{"key": k, "name": config.REGIONS[k]["name_ar"], "tz": config.REGIONS[k]["tz"],
                         "attribution": config.REGIONS[k]["attribution"]} for k in config.REGION_KEYS]}


def _region_cams(region: str | None) -> list[dict]:
    return [_camera_summary(c) for c in pipeline.cameras(region=region or None)]


@app.get("/api/cameras")
def list_cameras(region: str | None = None):
    return [_camera_summary(c) for c in pipeline.cameras(enabled_only=False, region=region or None)]


@app.get("/api/summary")
def summary(region: str | None = None):
    cams = _region_cams(region)
    ids = [c["id"] for c in cams]
    marks = ",".join("?" * len(ids)) or "''"
    levels = {k: 0 for k in ("low", "medium", "high", "critical")}
    for c in cams:
        if c["risk"]:
            levels[c["risk"]["level"]] += 1
    # مؤشر الحالة المعتمد = المُنعَّم من تقييم المخاطر، وإلا آخر لقطة
    cis = [(c["risk"] or {}).get("ci") or c["last_snapshot"]["condition_index"] for c in cams if c["last_snapshot"]]
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    priorities = sorted((c for c in cams if c["risk"]), key=lambda c: -(c["risk"]["priority"] or 0))
    # متوسط مؤشر الحالة أسبوعيًا (لمخطط الاتجاه العام)
    trend = db.query(f"""SELECT substr(ts,1,10) d, AVG(condition_index) ci FROM snapshots
                        WHERE condition_index IS NOT NULL AND kind IN ('seed','weekly','manual') AND camera_id IN ({marks})
                        GROUP BY strftime('%Y-%W', ts) ORDER BY d""", ids)
    return {
        "cameras": len(cams), "levels": levels,
        "awaiting": sum(1 for c in cams if not c["last_snapshot"]),
        "avg_condition": round(sum(cis) / len(cis), 1) if cis else None,
        "open_alerts": db.one(f"SELECT COUNT(*) n FROM alerts WHERE ack=0 AND camera_id IN ({marks})", ids)["n"],
        "alerts_7d": db.one(f"SELECT COUNT(*) n FROM alerts WHERE ts>? AND camera_id IN ({marks})", [week_ago] + ids)["n"],
        "below_threshold": sum(1 for v in cis if v <= config.MAINTENANCE_THRESHOLD),
        "snapshots": db.one(f"SELECT COUNT(*) n FROM snapshots WHERE camera_id IN ({marks})", ids)["n"],
        "priorities": priorities, "network_trend": trend,
        "lifecycle": lifecycle.kpis(ids),
        "seeding": state["seeding"],
    }


def _issue_out(i: dict) -> dict:
    db.loads(i, "track_ids", "events")
    i["stage_ar"] = lifecycle.STAGE_AR.get(i["stage"], i["stage"])
    i["kind_ar"] = lifecycle.KIND_AR.get(i["kind"], i["kind"])
    i["resolution_ar"] = lifecycle.RESOLUTION_AR.get(i["resolution"] or "", None)
    return i


@app.get("/api/issues")
def list_issues(region: str | None = None, stage: str | None = None, limit: int = Query(300, le=1000)):
    sql = "SELECT i.*, c.name camera_name, c.region FROM issues i JOIN cameras c ON c.id=i.camera_id WHERE 1=1"
    params: list = []
    if region:
        sql += " AND c.region=?"
        params.append(region)
    if stage:
        sql += " AND i.stage=?"
        params.append(stage)
    rows = db.query(sql + " ORDER BY COALESCE(i.resolved_ts, i.detected_ts, i.predicted_ts) DESC LIMIT ?", params + [limit])
    return [_issue_out(r) for r in rows]


@app.get("/api/cameras/{cam_id}")
def camera_detail(cam_id: str):
    cam = pipeline.get_camera(cam_id)
    if not cam:
        raise HTTPException(404, "الكاميرا غير موجودة")
    hist = pipeline.history(cam_id)
    snaps = db.query("""SELECT id,ts,kind,condition_index,pothole_count,crack_density,changed_pct,quality
                        FROM snapshots WHERE camera_id=? ORDER BY ts DESC LIMIT 120""", (cam_id,))
    return {
        **_camera_summary(cam),
        "source": {k: v for k, v in cam["source"].items() if k in ("type", "seed", "deterioration_rate", "camera_id")},
        "history": [{k: h[k] for k in ("id", "ts", "kind", "condition_index", "crack_density", "pothole_count", "changed_pct")} for h in hist],
        "latest_metrics": hist[-1]["metrics"] if hist else None,
        "snapshots": snaps,
        "risk_detail": pipeline.latest_risk(cam_id),
        "risk_history": db.query("SELECT ts,score,level FROM risk WHERE camera_id=? ORDER BY ts", (cam_id,)),
        "alerts": db.query("SELECT * FROM alerts WHERE camera_id=? ORDER BY ts DESC LIMIT 30", (cam_id,)),
        "maintenance": db.query("SELECT * FROM maintenance WHERE camera_id=? ORDER BY date DESC", (cam_id,)),
        "issues": [_issue_out(i) for i in db.query("SELECT * FROM issues WHERE camera_id=? ORDER BY id DESC", (cam_id,))],
        "tracks": [{**db.loads(t, "bbox", "areas"), "growth_pct_week": lifecycle.growth(t)} for t in db.query(
            "SELECT * FROM tracks WHERE camera_id=? AND status!='tentative' ORDER BY last_ts DESC LIMIT 40", (cam_id,))],
        "labels": vision.LABELS_AR,
    }


@app.get("/api/snapshots/{sid}/image")
def snapshot_image(sid: int, annotated: bool = False):
    s = db.one("SELECT image_path, annotated_path FROM snapshots WHERE id=?", (sid,))
    if not s:
        raise HTTPException(404)
    rel = s["annotated_path"] if annotated and s["annotated_path"] else s["image_path"]
    path = (config.DATA_DIR / rel).resolve()
    if not path.is_relative_to(config.DATA_DIR.resolve()) or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/alerts")
def list_alerts(limit: int = Query(100, le=500), unacked: bool = False):
    sql = "SELECT a.*, c.name camera_name, c.lat, c.lng FROM alerts a JOIN cameras c ON c.id=a.camera_id"
    if unacked:
        sql += " WHERE a.ack=0"
    return db.query(sql + " ORDER BY a.ts DESC LIMIT ?", (limit,))


@app.post("/api/alerts/{aid}/ack", dependencies=[Depends(admin)])
def ack_alert(aid: int):
    with db.tx() as c:
        c.execute("UPDATE alerts SET ack=1 WHERE id=?", (aid,))
    return {"ok": True}


@app.post("/api/cameras/{cam_id}/capture", dependencies=[Depends(admin)])
def capture_now(cam_id: str):
    """يبدأ الالتقاط في الخلفية: دفعة الإطارات قد تستغرق دقائق مع الكاميرات بطيئة التجدد."""
    if not pipeline.get_camera(cam_id):
        raise HTTPException(404)
    threading.Thread(target=pipeline.run_capture, args=(cam_id, "manual"), daemon=True).start()
    return {"ok": True, "started": True}


class MaintenanceIn(BaseModel):
    date: date
    action: str = Field(min_length=2, max_length=200)
    notes: str = Field(default="", max_length=1000)


@app.post("/api/cameras/{cam_id}/maintenance", dependencies=[Depends(admin)])
def add_maintenance(cam_id: str, m: MaintenanceIn):
    if not pipeline.get_camera(cam_id):
        raise HTTPException(404)
    mid = db.insert("maintenance", {"camera_id": cam_id, "date": m.date.isoformat(), "action": m.action, "notes": m.notes})
    closed = lifecycle.maintenance_logged(pipeline.get_camera(cam_id), m.date.isoformat(), m.action)
    return {"ok": True, "id": mid, "issues_resolved": closed}


class CameraIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]{2,40}$")
    name: str = Field(min_length=2, max_length=120)
    road: str = Field(default="—", max_length=120)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    source: dict
    meta: dict = Field(default_factory=dict)
    region: str = Field(default_factory=lambda: config.REGION_KEYS[0])


@app.post("/api/cameras", dependencies=[Depends(admin)])
def add_camera(cam: CameraIn):
    typ = cam.source.get("type")
    if typ not in ("snapshot", "mjpeg", "rtsp", "hls", "demo", "datagovsg", "az511", "fl511", "caltrans"):
        raise HTTPException(400, "نوع مصدر غير مدعوم")
    if typ not in ("demo", "datagovsg", "az511", "fl511") and not re.match(r"^(https?|rtsp)://", str(cam.source.get("url", ""))):
        raise HTTPException(400, "رابط المصدر غير صالح")
    import json
    with db.tx() as c:
        c.execute("INSERT OR REPLACE INTO cameras(id,name,road,lat,lng,source,meta,region) VALUES (?,?,?,?,?,?,?,?)",
                  (cam.id, cam.name, cam.road, cam.lat, cam.lng, json.dumps(cam.source, ensure_ascii=False),
                   json.dumps(cam.meta, ensure_ascii=False), cam.region if cam.region in config.REGIONS else config.REGION_KEYS[0]))
    return {"ok": True, "first_capture": pipeline.run_capture(cam.id, "manual")}


@app.get("/api/export/priorities.csv")
def export_csv(region: str | None = None):
    from fastapi.responses import Response
    rows = summary(region)["priorities"]
    lines = ["rank,camera_id,name,road,lat,lng,risk_score,level,prob_90d,condition_index,weeks_to_threshold,top_factor"]
    for i, c in enumerate(rows, 1):
        r, s = c["risk"], c["last_snapshot"] or {}
        lines.append(",".join(str(x).replace(",", " ") for x in (
            i, c["id"], c["name"], c["road"], c["lat"], c["lng"], r["score"], r["level"], r["prob_90d"],
            s.get("condition_index"), r["weeks_to_threshold"], r["top_factor"])))
    return Response("﻿" + "\n".join(lines), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=darb-priorities.csv"})


app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
