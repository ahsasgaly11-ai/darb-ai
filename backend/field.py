"""الرصد الميداني: يغطي ما بين الكاميرات الثابتة (التي ترى ~200 م فقط من الطريق).

1. بلاغات المواطنين وصور مركبات الأسطول: صورة + موقع ← تحقق آلي بنموذجَي الكشف ← ربط بأقرب كاميرا.
   في الموقع المجاني تصل البلاغات عبر GitHub Issues ويعالجها التشغيل اليومي (ingest_github).
2. خشونة الطريق من حساسات الهاتف: تسارع رأسي + سرعة GPS ← تقدير مؤشر IRI (م/كم) لكل ثانية قيادة،
   تُجمّع في خلايا ~100 م لتظهر طبقةً على الخريطة.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import re
from datetime import datetime, timezone

import cv2
import numpy as np

from . import config, db, gulf, vision

log = logging.getLogger("darb.field")
KINDS = {"pothole": "حفرة", "cracks": "تشققات", "sand": "رمال على الطريق", "water": "تجمّع مياه", "debris": "مخلّفات", "other": "أخرى"}
FULL = [[0, 0.25], [1, 0.25], [1, 1], [0, 1]]  # صورة الهاتف: الطريق في الثلاثة أرباع السفلية غالبًا
CELL = 0.001  # ~100 م


def km(lat1, lng1, lat2, lng2) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def nearest_region(lat: float, lng: float) -> str:
    return min(config.REGION_KEYS, key=lambda k: km(lat, lng, config.REGIONS[k]["lat"], config.REGIONS[k]["lng"]))


def nearest_camera(lat: float, lng: float, max_m: float = 500) -> tuple[str | None, float | None]:
    best = min(((c["id"], km(lat, lng, c["lat"], c["lng"]) * 1000) for c in db.query("SELECT id, lat, lng FROM cameras WHERE enabled=1")),
               key=lambda x: x[1], default=(None, None))
    return best if best[1] is not None and best[1] <= max_m else (None, None)


def decode_image(data: str | bytes) -> np.ndarray | None:
    """صورة من bytes أو data URL (base64). تُصغَّر إلى 1280 عرضًا مثل صور الكاميرات."""
    if isinstance(data, str):
        data = base64.b64decode(data.split(",", 1)[-1])
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is not None and img.shape[1] > 1280:
        img = cv2.resize(img, (1280, int(img.shape[0] * 1280 / img.shape[1])), interpolation=cv2.INTER_AREA)
    return img


def verify(img: np.ndarray, kind: str) -> dict:
    """تحقق آلي: هل تُظهر الصورة ما يقوله البلاغ؟ لا رفض آلي — ما لم يتأكد يذهب لمراجعة بشرية."""
    r = vision.analyze(img, FULL, use_ai=True)
    sand = gulf.sand_cover(img, FULL)
    found = {"pothole": r["pothole_count"] > 0,
             "cracks": r["crack_count"] > 0,
             "sand": sand >= 0.10}.get(kind, r["pothole_count"] > 0 or r["crack_count"] > 0)
    return {"verified": bool(found), "engine": r["engine"], "pothole_count": r["pothole_count"], "crack_count": r["crack_count"],
            "crack_density": r["crack_density"], "condition_index": r["condition_index"], "sand_cover": sand,
            "by_type": r["by_type"], "_result": r}


def create_report(lat: float, lng: float, kind: str, note: str = "", image: str | bytes | None = None,
                  source: str = "citizen", ref: str | None = None, ts: str | None = None) -> dict:
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("موقع غير صالح")
    kind = kind if kind in KINDS else "other"
    if ref and db.one("SELECT id FROM reports WHERE source=? AND ref=?", (source, ref)):
        raise ValueError("البلاغ مسجّل مسبقًا")
    ts = ts or datetime.now(timezone.utc).isoformat(timespec="seconds")
    cam_id, dist = nearest_camera(lat, lng)
    row = {"ts": ts, "source": source, "ref": ref, "lat": lat, "lng": lng, "region": nearest_region(lat, lng),
           "kind": kind, "note": note[:500], "status": "no_image", "camera_id": cam_id, "distance_m": dist and round(dist)}
    img = decode_image(image) if image else None
    if img is not None:
        v = verify(img, kind)
        result = v.pop("_result")
        stamp = ts.replace(":", "").replace("-", "")[:15]
        base = config.SNAPSHOT_DIR / "_reports" / f"{stamp}_{source}"
        base.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(base.with_suffix(".jpg")), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        cv2.imwrite(str(base.with_name(base.name + "_ann.jpg")), vision.annotate(img, result, FULL), [cv2.IMWRITE_JPEG_QUALITY, 85])
        row.update(image_path=str(base.with_suffix(".jpg").relative_to(config.DATA_DIR)),
                   annotated_path=str(base.with_name(base.name + "_ann.jpg").relative_to(config.DATA_DIR)),
                   ai=v, status="verified" if v["verified"] else "review")
    rid = db.insert("reports", row)
    if row["status"] == "verified" and cam_id:  # بلاغ مؤكد قرب كاميرا: تنبيه على مقطعها
        from . import pipeline
        cam = pipeline.get_camera(cam_id)
        if cam:
            pipeline.add_alert(cam, ts, "field_report", "warning",
                               f"بلاغ ميداني مؤكد بالذكاء الاصطناعي: {KINDS[kind]} على بعد ~{row['distance_m']} م من الكاميرا.")
    return {"id": rid, **{k: row[k] for k in ("status", "kind", "region", "camera_id", "distance_m")}, "ai": row.get("ai") or {}}


def list_reports(region: str | None = None, limit: int = 300) -> list[dict]:
    q, params = "SELECT * FROM reports", []
    if region:
        q, params = q + " WHERE region=?", [region]
    rows = db.query(q + " ORDER BY ts DESC LIMIT ?", params + [limit])
    for r in rows:
        r["ai"] = json.loads(r["ai"] or "{}")
        r["kind_ar"] = KINDS.get(r["kind"], r["kind"])
    return rows


# ---------- خشونة الطريق من الهاتف ----------

def iri_estimate(rms_az: float, speed_ms: float) -> float:
    """تقدير IRI (م/كم) من جذر متوسط مربع التسارع الرأسي (م/ث²) خلال ثانية، مصحّحًا بالسرعة:
    الاهتزاز يزداد مع السرعة لنفس الخشونة، فيُطبَّع إلى 20 م/ث (72 كم/س). معايرة تقريبية من أبحاث
    القياس بالهواتف (ارتباط خطي بين RMS التسارع وIRI)؛ تُحسَّن بمعايرة على مقاطع معروفة الخشونة."""
    v = max(speed_ms, 5.0)
    return round(max(0.5, 0.9 + 2.1 * rms_az * math.sqrt(20.0 / v)), 2)


def add_roughness(device: str, points: list[dict]) -> int:
    """نقاط قيادة: [{lat, lng, iri | rms, speed, ts}] — النقاط تحت 15 كم/س تُهمَل (ازدحام/توقف يشوّه القياس)."""
    rows = []
    for p in points[:20000]:
        try:
            lat, lng, speed = float(p["lat"]), float(p["lng"]), float(p.get("speed") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if speed < 4.2 or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        iri = float(p["iri"]) if p.get("iri") is not None else iri_estimate(float(p.get("rms", 0)), speed)
        if not 0.3 <= iri <= 25:
            continue
        rows.append((p.get("ts") or datetime.now(timezone.utc).isoformat(timespec="seconds"), re.sub(r"[^\w-]", "", device)[:40] or "anon",
                     lat, lng, iri, speed))
    with db.tx() as c:
        c.executemany("INSERT INTO roughness(ts,device,lat,lng,iri,speed) VALUES (?,?,?,?,?,?)", rows)
    return len(rows)


def roughness_cells(region: str | None = None) -> list[dict]:
    """متوسط الخشونة لكل خلية ~100 م (وسيط القراءات يقاوم المطبات والحفر المنفردة)."""
    cells: dict[tuple, list[float]] = {}
    for r in db.query("SELECT lat, lng, iri FROM roughness"):
        cells.setdefault((round(r["lat"] / CELL) * CELL, round(r["lng"] / CELL) * CELL), []).append(r["iri"])
    out = []
    for (lat, lng), v in cells.items():
        if region and nearest_region(lat, lng) != region:
            continue
        iri = float(np.median(v))
        out.append({"lat": round(lat, 5), "lng": round(lng, 5), "iri": round(iri, 2), "n": len(v), "class": iri_class(iri)})
    return out


def iri_class(iri: float) -> str:
    return "excellent" if iri < 2 else "good" if iri < 4 else "fair" if iri < 6 else "poor" if iri < 8 else "very_poor"


# ---------- بلاغات GitHub (للموقع المجاني) ----------

def parse_issue(issue: dict) -> dict | None:
    """بلاغ من GitHub Issue عنوانه يبدأ بـ «[بلاغ]» وفيه سطور: النوع، الموقع (lat,lng)، الملاحظة، وصورة مرفقة."""
    if not str(issue.get("title", "")).startswith("[بلاغ]") or issue.get("pull_request"):
        return None
    body = issue.get("body") or ""
    m = re.search(r"(-?\d{1,2}\.\d{3,})\s*[,،]\s*(-?\d{1,3}\.\d{3,})", body)
    if not m:
        return None
    kind = next((k for k, ar in KINDS.items() if ar in body or f"`{k}`" in body), "other")
    img = re.search(r"!\[[^\]]*\]\((https://[^)\s]+)\)|<img[^>]+src=\"(https://[^\"]+)\"", body)
    note = re.search(r"الملاحظة[:：]\s*(.+)", body)
    return {"lat": float(m.group(1)), "lng": float(m.group(2)), "kind": kind, "image_url": img and (img.group(1) or img.group(2)),
            "note": note.group(1).strip()[:300] if note else "", "ref": str(issue["number"]), "ts": issue.get("created_at")}


def ingest_github(repo: str, token: str) -> int:
    """يقرأ بلاغات GitHub المفتوحة، يتحقق منها بالذكاء الاصطناعي، يرد على صاحب البلاغ ويغلقه."""
    import httpx

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": config.USER_AGENT}
    done = 0
    with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as gh:
        issues = gh.get(f"https://api.github.com/repos/{repo}/issues", params={"state": "open", "per_page": 50}).json()
        for issue in issues if isinstance(issues, list) else []:
            rep = parse_issue(issue)
            if not rep:
                continue
            msg = None
            try:
                image = gh.get(rep["image_url"]).content if rep["image_url"] else None
                out = create_report(rep["lat"], rep["lng"], rep["kind"], rep["note"], image, "github", rep["ref"], rep["ts"])
                ai = out["ai"]
                verdict = {"verified": "✅ **تأكد آليًا**", "review": "🔎 **لم يتأكد آليًا** — سيراجعه مختص", "no_image": "📍 **سُجّل بلا صورة** — أرفق صورة لتسريع التحقق"}[out["status"]]
                details = f"حفر: {ai.get('pothole_count', 0)} · تشققات: {ai.get('crack_count', 0)}" if ai else ""
                near = f"\n- أقرب كاميرا مراقبة على بعد ~{out['distance_m']} م وأُضيف تنبيه لمقطعها." if out["camera_id"] else ""
                msg = f"شكرًا لبلاغك 🙏\n\n- النتيجة: {verdict}\n- {details}{near}\n- يظهر البلاغ الآن على خريطة دَرْب.\n\n---\n_دَرْب AI — تحقق آلي_"
            except ValueError as e:
                msg = f"تعذّر تسجيل البلاغ: {e}"
            except Exception:
                log.exception("github report %s failed", rep["ref"])
                continue
            gh.post(f"https://api.github.com/repos/{repo}/issues/{rep['ref']}/comments", json={"body": msg})
            gh.patch(f"https://api.github.com/repos/{repo}/issues/{rep['ref']}", json={"state": "closed", "state_reason": "completed"})
            done += 1
    return done
