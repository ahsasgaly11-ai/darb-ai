"""المسار الكامل لكل التقاط: صور → خلفية بلا مركبات → كشف العيوب → مقارنة باللقطة السابقة
→ تقدير المخاطر والتنبؤ → تنبيهات. يُستدعى من المجدول (أسبوعي/يومي) أو يدويًا من الواجهة.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import httpx
import numpy as np

from . import change, config, db, gulf, incidents, lifecycle, risk, sources, vision, weather

log = logging.getLogger("darb.pipeline")
_cam_locks: dict[str, threading.Lock] = {}
followup_hook = None  # يضبطه المجدول: جدولة فحص متابعة قريب لكاميرا عليها اشتباه

ALERT_TEXT = {
    "sudden_change": "تغيّر مفاجئ في سطح الطريق",
    "new_pothole": "حفرة جديدة",
    "threshold": "بلوغ عتبة الصيانة",
    "risk_up": "ارتفاع مستوى الخطر",
    "capture_failed": "تعذّر الالتقاط من الكاميرا",
    "low_quality": "جودة الصورة غير كافية للتحليل",
    "incident": "حادث مروري قرب الكاميرا",
    "view_changed": "تغيّر زاوية الكاميرا",
    "view_lost": "الكاميرا حُرّكت بعيدًا عن منطقة الطريق",
    "predicted": "تنبؤ بتدهور قادم",
    "resolved": "رُصدت معالجة المشكلة",
    "recurrence": "عودة المشكلة بعد الإصلاح",
    "scene_change": "تغيّر في المشهد",
}


# ---------- الكاميرات ----------

def tz(cam: dict) -> ZoneInfo:
    return ZoneInfo(config.tz_of(cam.get("region", "")))


def sync_cameras(now: datetime | None = None) -> None:
    """مزامنة ملفات كاميرات المناطق المفعّلة مع قاعدة البيانات (الكاميرات المضافة من الواجهة تبقى كما هي)."""
    now = now or datetime.now(timezone.utc)
    for region, path in config.camera_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        for cam in data.get("cameras", []):
            existing = db.one("SELECT source FROM cameras WHERE id=?", (cam["id"],))
            prev_src = json.loads(existing["source"]) if existing else {}
            src = dict(cam["source"])
            # أحداث المحاكاة النسبية («قبل N أيام») تُثبَّت بتاريخ مطلق عند أول تشغيل
            for key in ("sudden_event", "repair_event"):
                ev = src.get(key)
                if ev and "days_ago" in ev and not ev.get("at"):
                    at = prev_src.get(key, {}).get("at") or (now - timedelta(days=ev["days_ago"])).replace(
                        hour=3, minute=0, second=0, microsecond=0).isoformat()
                    src[key] = {**ev, "at": at}
            ev = src.get("sudden_event")
            if ev and "clear_after_days" in ev and ev.get("at") and not ev.get("clear_at"):
                src["sudden_event"]["clear_at"] = (datetime.fromisoformat(ev["at"]) + timedelta(days=ev["clear_after_days"])).isoformat()
            with db.tx() as c:
                c.execute("""INSERT INTO cameras(id,name,road,lat,lng,source,meta,region) VALUES (?,?,?,?,?,?,?,?)
                             ON CONFLICT(id) DO UPDATE SET name=excluded.name, road=excluded.road, lat=excluded.lat,
                             lng=excluded.lng, source=excluded.source, meta=excluded.meta, region=excluded.region""",
                          (cam["id"], cam["name"], cam["road"], cam["lat"], cam["lng"],
                           json.dumps(src, ensure_ascii=False), json.dumps(cam.get("meta", {}), ensure_ascii=False), region))


def get_camera(cam_id: str) -> dict | None:
    cam = db.loads(db.one("SELECT * FROM cameras WHERE id=?", (cam_id,)), "source", "meta")
    if cam:
        m = db.one("SELECT date FROM maintenance WHERE camera_id=? ORDER BY date DESC LIMIT 1", (cam_id,))
        if m:
            cam["meta"]["last_maintenance"] = m["date"]
    return cam


def cameras(enabled_only: bool = True, region: str | None = None) -> list[dict]:
    where, params = [], []
    if enabled_only:
        where.append("enabled=1")
    if region:
        where.append("region=?")
        params.append(region)
    sql = "SELECT id FROM cameras" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY region, id"
    return [get_camera(r["id"]) for r in db.query(sql, params)]


def history(cam_id: str, limit: int = 400) -> list[dict]:
    rows = db.query("""SELECT id,ts,kind,condition_index,crack_density,pothole_count,changed_pct,quality,metrics
                       FROM snapshots WHERE camera_id=? AND condition_index IS NOT NULL
                       ORDER BY ts DESC LIMIT ?""", (cam_id, limit))
    rows.reverse()
    for r in rows:
        db.loads(r, "metrics")
    return rows


def latest_risk(cam_id: str) -> dict | None:
    return db.loads(db.one("SELECT * FROM risk WHERE camera_id=? ORDER BY ts DESC LIMIT 1", (cam_id,)),
                    "factors", "forecast", "recommendations")


# ---------- التنبيهات ----------

def add_alert(cam: dict, ts: str, typ: str, severity: str, message: str, snapshot_id: int | None = None) -> dict:
    title = f"{ALERT_TEXT.get(typ, typ)} — {cam['name']}"
    row = {"camera_id": cam["id"], "ts": ts, "type": typ, "severity": severity, "title": title,
           "message": message, "snapshot_id": snapshot_id,
           # ملاحظات المراجعة البصرية لا تُحسب ضمن التنبيهات المفتوحة
           "ack": 1 if typ == "scene_change" else 0}
    row["id"] = db.insert("alerts", row)
    if config.ALERT_WEBHOOK:
        try:
            httpx.post(config.ALERT_WEBHOOK, json={**row, "text": f"{title}\n{message}",
                                                   "lat": cam["lat"], "lng": cam["lng"]}, timeout=10)
        except Exception as e:
            log.warning("webhook failed: %s", e)
    return row


# ---------- الالتقاط والتحليل ----------

REF_WIDTH = 960  # دقة صور مرجع المنظر (أعلى من 640 تزيد النقاط المتطابقة بين لقطتين بإضاءتين مختلفتين)


def camera_views(cam: dict) -> list[list[list[float]]]:
    """مناطق الطريق المرسومة للكاميرا: الأساسية ثم مناظر إضافية. كاميرات كثيرة تدور بين أوضاع ثابتة خلال اليوم
    (اتجاه آخر، تكبير)، ولكل وضع منطقته وصورة مرجعه في config/roi_ref/<الكاميرا>-<بصمة المنطقة>.jpg."""
    return [sources.default_roi(cam)] + [v["roi"] for v in cam.get("meta", {}).get("views", [])]


def _roi_key(roi) -> str:
    return hashlib.sha1(json.dumps(roi).encode()).hexdigest()[:8]


def _period(cam: dict, at: datetime | None) -> int:
    """فترة اليوم (كل 3 ساعات محليًا): لكل فترة مرجع متجدد، فظلال الصباح لا تُقارن بظلال العصر."""
    return (at or datetime.now(timezone.utc)).astimezone(tz(cam)).hour // 3


def _view_files(cam: dict, at: datetime | None = None) -> tuple[str, Path, Path]:
    d = config.DATA_DIR / "roi_ref"
    p = _period(cam, at)
    return _roi_key(camera_views(cam)), d / f"{cam['id']}-t{p}.jpg", d / f"{cam['id']}-t{p}.json"


def _rolling_refs(cam: dict, key: str, at: datetime | None) -> list[tuple[Path, list]]:
    """المراجع المتجددة للكاميرا: فترة اليوم الحالية أولًا، ثم بقية الفترات (والمرجع القديم بلا فترة)."""
    d, cur = config.DATA_DIR / "roi_ref", _period(cam, at)
    out = []
    for meta_p in sorted(d.glob(f"{cam['id']}*.json"), key=lambda q: q.stem != f"{cam['id']}-t{cur}"):
        if meta_p.stem != cam["id"] and not meta_p.stem.startswith(f"{cam['id']}-t"):
            continue  # كاميرا أخرى يبدأ اسمها بالاسم نفسه
        try:
            meta = json.loads(meta_p.read_text())
        except (OSError, ValueError):
            continue
        if meta.get("key") == key and meta_p.with_suffix(".jpg").exists():
            out.append((meta_p.with_suffix(".jpg"), meta["roi"]))
    return out


def drawn_ref(cam: dict, roi) -> Path:
    return config.ROOT / "config" / "roi_ref" / f"{cam['id']}-{_roi_key(roi)}.jpg"


def roi_for_view(cam: dict, img: np.ndarray, at: datetime | None = None) -> tuple[list[list[float]], str]:
    """منطقة الطريق في منظر الكاميرا الحالي. كاميرات الطرق السريعة PTZ يحرّكها المشغّلون خلال اليوم، فتُقارن
    اللقطة بمراجع المنظر: آخر لقطة ناجحة (مرجع متجدد بإضاءة الساعة نفسها أمس) وصور المناظر المرسومة يدويًا.
    أفضل تطابق يحدد المنطقة، وتُنقل إلى المنظر الحالي بالـHomography إذا تحرّكت الكاميرا قليلًا.
    تعيد (المنطقة، الحالة): same | moved (نُقلت) | new (لا مرجع: تصير هذه اللقطة مرجعًا) | lost (منظر غير معروف)."""
    views = camera_views(cam)
    if cam["source"].get("type") == "demo":
        return views[0], "same"  # المحاكاة منظرها ثابت
    key = _view_files(cam, at)[0]
    refs = _rolling_refs(cam, key, at) + [(drawn_ref(cam, v), v) for v in views if drawn_ref(cam, v).exists()]
    if not refs:
        return views[0], "new"
    best = (None, 0, None)
    for path, roi in refs:
        H, n = change.homography(cv2.imread(str(path)), img)
        if H is not None and n > best[1]:
            best = (H, n, roi)
        if n >= 150:
            break  # تطابق قوي: لا داعي لتجربة البقية
    H, _, roi = best
    if H is None:
        return views[0], "lost"
    h, w = img.shape[:2]
    pts = np.float32([[x * w, y * h] for x, y in roi])
    moved = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), H).reshape(-1, 2)
    if np.abs(moved - pts).max() < 0.03 * w:
        return roi, "same"  # اهتزاز أو فرق محاذاة بسيط: المنطقة كما هي
    full = abs(cv2.contourArea(moved))
    inside = np.zeros((h, w), np.uint8)
    cv2.fillPoly(inside, [np.round(moved).astype(np.int32)], 1)
    area0 = abs(cv2.contourArea(pts))
    if not (0.2 * area0 < full < 5 * area0) or inside.sum() < 0.6 * full or inside.sum() < 0.01 * w * h:
        return views[0], "lost"  # المنطقة خرجت من الإطار أو تحويل غير معقول
    return [[round(min(1.0, max(0.0, float(x) / w)), 4), round(min(1.0, max(0.0, float(y) / h)), 4)] for x, y in moved], "moved"


def remember_view(cam: dict, img: np.ndarray, roi: list[list[float]], at: datetime | None = None) -> None:
    """لقطة ناجحة تصير مرجع المنظر لهذه الفترة من اليوم (مع المنطقة التي حُلّلت بها)."""
    if cam["source"].get("type") == "demo":
        return
    key, ref_img, ref_meta = _view_files(cam, at)
    ref_img.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ref_img), _ref_size(img), [cv2.IMWRITE_JPEG_QUALITY, 85])
    ref_meta.write_text(json.dumps({"key": key, "roi": roi}))


def _ref_size(img: np.ndarray) -> np.ndarray:
    w = min(REF_WIDTH, img.shape[1])
    return cv2.resize(img, (w, int(img.shape[0] * w / img.shape[1])), interpolation=cv2.INTER_AREA)


def _save(img: np.ndarray, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return str(path.relative_to(config.DATA_DIR))


def load_image(rel: str) -> np.ndarray | None:
    p = config.DATA_DIR / rel
    return cv2.imread(str(p)) if p.exists() else None


def run_capture(cam_id: str, kind: str = "manual", at: datetime | None = None,
                n_frames: int | None = None, interval: float | None = None, frames=None) -> dict:
    """frames: إطارات التُقطت مسبقًا (التشغيل اليومي يلتقط كل الكاميرات بالتوازي ثم يحلّلها بالتتابع)،
    أو استثناء الالتقاط إن فشل."""
    lock = _cam_locks.setdefault(cam_id, threading.Lock())
    with lock:
        return _run_capture(cam_id, kind, at, n_frames, interval, frames)


def _run_capture(cam_id, kind, at, n_frames, interval, frames=None) -> dict:
    cam = get_camera(cam_id)
    if cam is None:
        raise KeyError(cam_id)
    at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ts = at.isoformat(timespec="seconds")
    if n_frames is None:
        n_frames = config.SENTINEL_BURST_FRAMES if kind == "sentinel" else config.BURST_FRAMES

    try:
        if isinstance(frames, Exception):
            raise frames
        if not frames:
            frames = sources.capture(cam, at, n_frames, interval)
    except Exception as e:
        log.warning("capture failed for %s: %s", cam_id, e)
        recent = db.one("SELECT id FROM alerts WHERE camera_id=? AND type='capture_failed' AND ts>?",
                        (cam_id, (at - timedelta(hours=24)).isoformat()))
        if not recent:
            add_alert(cam, ts, "capture_failed", "warning", f"الخطأ: {e}")
        return {"ok": False, "error": str(e)}

    bg, first = sources.background(frames), frames
    roi, view = roi_for_view(cam, bg, at)
    occ = sources.occlusion(frames, roi)
    if occ > config.CONGESTION_OCCLUSION and cam["source"].get("type") == "datagovsg":
        # ازدحام يحجب الطريق: المصادر ذات الأرشيف تسمح بتجربة لحظات قريبة واختيار أوضحها
        for minutes in (-20, -40, 20, -60):
            alt = at + timedelta(minutes=minutes)
            if alt > datetime.now(timezone.utc):
                continue
            try:
                f2 = sources.capture(cam, alt, n_frames, interval)
            except Exception:
                continue
            o2 = sources.occlusion(f2, roi)
            if o2 < occ:
                frames, occ = f2, o2
            if occ <= config.CONGESTION_OCCLUSION:
                break
    img = bg if frames is first else sources.background(frames)  # الأرشيف قد يستبدل الدفعة بلحظة أقل ازدحامًا
    q = vision.quality(img)
    q["occlusion"] = occ
    if q["status"] == "ok" and occ > config.CONGESTION_OCCLUSION:
        q["status"] = "congested"
    stamp = at.astimezone(tz(cam)).strftime("%Y%m%dT%H%M%S")
    base = config.SNAPSHOT_DIR / cam_id / f"{stamp}_{kind}"
    image_path = _save(img, base.with_suffix(".jpg"))

    if view == "lost":
        # الكاميرا موجّهة إلى منظر آخر: التحليل بالمنطقة القديمة يقرأ أكتافًا أو أشجارًا. يُعاد في التشغيل التالي
        # (قد يعيدها المشغّل إلى وضعها)، وإن استمر فالمنطقة تحتاج مراجعة على المنظر الجديد
        sid = db.insert("snapshots", {"camera_id": cam_id, "ts": ts, "kind": kind, "image_path": image_path,
                                      "quality": "view_lost", "metrics": {"quality": q, "view": view}})
        if _view_lost_persists(cam, ts) and not db.one("SELECT id FROM alerts WHERE camera_id=? AND type='view_lost' AND ts>?",
                                                        (cam_id, (at - timedelta(hours=24)).isoformat())):
            add_alert(cam, ts, "view_lost", "warning",
                      "وُجّهت الكاميرا منذ يومين إلى منظر لا يطابق الذي حُدّدت عليه منطقة الطريق — لا تحليل حتى تعود أو تُراجَع المنطقة.", sid)
        return {"ok": False, "snapshot_id": sid, "quality": {**q, "status": "view_lost"}}
    if q["status"] != "ok":
        # لقطة غير صالحة للتحليل (ظلام/ضبابية/ازدحام): تُحفظ للسجل ولا تدخل الاتجاه ولا المقارنة
        sid = db.insert("snapshots", {"camera_id": cam_id, "ts": ts, "kind": kind, "image_path": image_path,
                                      "quality": q["status"], "metrics": {"quality": q}})
        if q["status"] != "congested":
            add_alert(cam, ts, "low_quality", "info", f"السطوع {q['brightness']}، الحدة {q['sharpness']} — ستُعاد المحاولة في الموعد التالي.", sid)
        return {"ok": False, "snapshot_id": sid, "quality": q}

    prev = db.one("""SELECT * FROM snapshots WHERE camera_id=? AND condition_index IS NOT NULL AND ts<?
                     ORDER BY ts DESC LIMIT 1""", (cam_id, ts))
    prev_img = load_image(prev["image_path"]) if prev else None
    use_ai = cam["source"].get("type") != "demo"  # المحاكاة مرسومة — يناسبها الكشف الكلاسيكي
    result, diff = _analyze(img, roi, prev_img, use_ai)
    confirmed = False
    if prev and config.CONFIRM_RECAPTURE and _suspicious(prev, result, diff):
        # تأكيد قبل التنبيه: دفعة ثانية بعد مهلة، ثم وسيط زمني على الدفعتين معًا —
        # المركبة المتوقفة أو الظل العابر يختفي، والحفرة الحقيقية تبقى
        try:
            target = at + timedelta(seconds=config.CONFIRM_DELAY)
            if cam["source"].get("type") != "demo":
                # اللقطة الحية تنتظر فعلًا؛ اللقطة التاريخية (سجل سابق) لحظتها في الماضي فلا انتظار
                wait = (target - datetime.now(timezone.utc)).total_seconds()
                if wait > 0:
                    time.sleep(wait)
            frames2 = sources.capture(cam, target, n_frames, interval)
            img = sources.background(frames + frames2)
            _save(img, base.with_suffix(".jpg"))
            result, diff = _analyze(img, roi, prev_img, use_ai)
            confirmed = True
        except Exception as e:
            log.warning("confirmation capture failed for %s: %s", cam_id, e)

    # تنبيه على مرحلتين: الاكتشاف الأول «اشتباه» فقط، ويُطلق التنبيه إذا بقي التغيّر في اللقطة التالية
    # مقارنةً بالمرجع نفسه (يستبعد الظلال وتغيّر الإضاءة والأجسام العابرة التي تختلف بين يوم وآخر)
    pending, suspect = None, None
    prev_metrics = json.loads(prev["metrics"]) if prev else {}
    prev_suspect = prev_metrics.get("suspect")
    ref = (db.one("SELECT * FROM snapshots WHERE id=?", (prev_metrics["suspect_ref"],))
           if prev_metrics.get("suspect_ref") and prev_suspect != "scene_change" else None)
    ref_img = load_image(ref["image_path"]) if ref else None
    if ref is not None and ref_img is not None:
        diff_ref = change.compare(ref_img, img, roi)
        cand = _sudden_alert(ref, result, diff_ref, True)
        # التأكيد يصحّ لنفس نوع الحدث فقط: اشتباه بتغيّر لا يؤكّد حفرة ظهرت لأول مرة الآن
        if cand and cand[0] == prev_suspect:
            pending, diff = cand, diff_ref
    if pending is None and prev and not diff.get("view_changed"):
        cand = _sudden_alert(prev, result, diff, confirmed)
        if cand and cand[1] != "info":
            suspect = {"suspect": cand[0], "suspect_ref": prev["id"]}
        elif cand:  # تغيّر في المشهد: ملاحظة للمراجعة فقط، لا اشتباه ولا مشكلة
            pending = cand

    annotated_path = _save(vision.annotate(img, result, roi, diff["boxes"]), base.with_name(base.name + "_ann.jpg"))
    metrics = {**result, "change": diff, "quality": q, "confirmed": confirmed, "view": view, **(suspect or {}),
               **({"roi": roi} if view == "moved" else {})}
    sid = db.insert("snapshots", {
        "camera_id": cam_id, "ts": ts, "kind": kind, "image_path": image_path, "annotated_path": annotated_path,
        "condition_index": result["condition_index"], "crack_density": result["crack_density"],
        "pothole_count": result["pothole_count"], "changed_pct": diff["changed_pct"], "quality": "ok",
        "metrics": metrics,
    })
    remember_view(cam, img, roi, at)

    alerts = []
    if diff.get("view_changed"):
        alerts.append(add_alert(cam, ts, "view_changed", "info",
                                "تغيّر منظر الكاميرا (دوران أو تكبير) — اعتُمدت هذه اللقطة مرجعًا جديدًا للمقارنة.", sid))
    elif (sand := _sand_alert(cam_id, ts, result)):
        alerts.append(add_alert(cam, ts, "sand", "warning", sand, sid))
    elif pending:
        typ, sev, msg = pending
        note = "" if sev == "info" else " (تأكّد في لقطتين متتاليتين)"
        alerts.append(add_alert(cam, ts, typ, sev, msg + note, sid))
    if suspect and followup_hook and abs((datetime.now(timezone.utc) - at).total_seconds()) < 600:
        followup_hook(cam_id)  # لقطة حية: فحص متابعة قريب بدل انتظار الموعد التالي

    assessment = assess_camera(cam, at)
    if assessment:
        prev_r = db.loads(db.one("SELECT level, forecast FROM risk WHERE camera_id=? AND ts<? ORDER BY ts DESC LIMIT 1",
                                 (cam_id, ts)), "forecast")
        # عتبة الصيانة تُقاس على المؤشر المُنعَّم (وسيط آخر 3 لقطات أسبوعية) لا على لقطة منفردة
        thr = config.MAINTENANCE_THRESHOLD
        prev_ci = (prev_r or {}).get("forecast", {}).get("ci") if prev_r else None
        if prev_ci is not None and prev_ci > thr >= assessment["ci"]:
            alerts.append(add_alert(cam, ts, "threshold", "critical",
                                    f"مؤشر الحالة المُنعَّم {assessment['ci']:.0f} أصبح دون عتبة الصيانة {thr:.0f}.", sid))
        order = ["low", "medium", "high", "critical"]
        if prev_r and order.index(assessment["level"]) > order.index(prev_r["level"]) and assessment["level"] in ("high", "critical"):
            alerts.append(add_alert(cam, ts, "risk_up", "warning",
                                    f"مستوى الخطر ارتفع إلى «{assessment['level_ar']}» (الدرجة {assessment['score']:.0f}/100). "
                                    f"أبرز العوامل: {assessment['factors'][0]['label']}.", sid))
        store_risk(cam_id, ts, assessment)
    try:  # دورة حياة المشكلة: قبل ← أثناء ← بعد
        lifecycle.update(cam, ts, result, assessment, alerts, add_alert)
    except Exception:
        log.exception("lifecycle update failed for %s", cam_id)
    return {"ok": True, "snapshot_id": sid, "condition_index": result["condition_index"], "suspect": bool(suspect),
            "risk": assessment and {k: assessment[k] for k in ("score", "level", "level_ar")}, "alerts": alerts}


def _sudden_alert(ref: dict, result: dict, diff: dict, confirmed: bool) -> tuple[str, str, str] | None:
    """قواعد التغيّر المفاجئ مقارنةً بلقطة مرجعية — تعيد (النوع، الخطورة، الرسالة) أو None."""
    ci_drop = ref["condition_index"] - result["condition_index"]
    new_potholes = result["pothole_count"] - (ref["pothole_count"] or 0)
    area_change = diff["changed_pct"] >= config.SUDDEN_CHANGE_PCT and diff["darker_ratio"] >= 0.5
    if str(result.get("engine", "")).startswith("ai") and area_change and ci_drop < 5 and new_potholes <= 0:
        # مع الذكاء الاصطناعي: فرق البكسلات وحده (ظلال الشمس، الغيوم، أرض مبتلة، مركبات) ليس دليلًا على عيب.
        # يُسجَّل للمراجعة البصرية فقط ولا يفتح مشكلة — قد يكون مخلّفات لا يعرفها النموذج
        return ("scene_change", "info",
                f"تغيّر في {diff['changed_pct']:.1f}% من المشهد دون عيب يكتشفه النموذج — غالبًا ظلال أو إضاءة أو مركبات؛ "
                "للمراجعة البصرية إن لزم.") if confirmed else None
    if area_change and (ci_drop >= 5 or new_potholes > 0):
        extra = f" ورُصدت {new_potholes} حفرة جديدة" if new_potholes > 0 else ""
        return ("sudden_change", "critical",
                f"تغيّر {diff['changed_pct']:.1f}% من مساحة الطريق{extra}، وانخفض مؤشر الحالة {ci_drop:.0f} نقطة. "
                "قد يكون حفرة مفاجئة أو هبوطًا أو مخلّفات — يوصى بفحص ميداني فوري.")
    if new_potholes > 0:
        return ("new_pothole", "critical",
                f"عدد الحفر المرصودة ارتفع من {ref['pothole_count']} إلى {result['pothole_count']}.")
    if area_change and confirmed:
        return ("sudden_change", "warning",
                f"تغيّر مستمر في {diff['changed_pct']:.1f}% من سطح الطريق — قد يكون مخلّفات أو انسكابًا أو تجمّع مياه "
                "أو أعمالًا على الطريق أو بداية هبوط. يوصى بالتحقق.")
    if ci_drop >= config.SUDDEN_CI_DROP:
        return ("sudden_change", "warning",
                f"انخفض مؤشر الحالة من {ref['condition_index']:.0f} إلى {result['condition_index']:.0f}.")
    return None


def _view_lost_persists(cam: dict, ts: str) -> bool:
    """«الكاميرا حُرّكت» يستحق تنبيهًا إذا تكرر في يومَي التقاط: المرة الواحدة قد تكون جولة مؤقتة للمشغّل أو إضاءة
    مختلفة جدًا عن المرجع، وتُعاد المحاولة تلقائيًا."""
    day = datetime.fromisoformat(ts).astimezone(tz(cam)).replace(hour=0, minute=0, second=0, microsecond=0)
    last = db.one("SELECT quality FROM snapshots WHERE camera_id=? AND ts<? ORDER BY ts DESC LIMIT 1",
                  (cam["id"], day.astimezone(timezone.utc).isoformat()))
    return bool(last and last["quality"] == "view_lost")


def revalidate_alerts() -> int:
    """يعيد فحص التنبيهات المفتوحة بالقواعد الحالية ويُقرّ ما لم يعد صحيحًا: «الكاميرا حُرّكت» إذا عادت الكاميرا
    (لقطة سليمة أحدث) أو لم يتكرر في يومين، و«الرمال» إذا لم يعد يتجاوز خط أساس الساعة نفسها."""
    n = 0
    for a in db.query("SELECT * FROM alerts WHERE ack=0 AND type IN ('view_lost','sand')"):
        cam = get_camera(a["camera_id"])
        if cam is None:
            continue
        if a["type"] == "view_lost":
            back = db.one("SELECT id FROM snapshots WHERE camera_id=? AND ts>? AND condition_index IS NOT NULL", (cam["id"], a["ts"]))
            stale = back or not _view_lost_persists(cam, a["ts"])
        else:
            snap = db.one("SELECT metrics FROM snapshots WHERE id=?", (a["snapshot_id"],)) if a["snapshot_id"] else None
            stale = snap is not None and _sand_excess(cam["id"], a["ts"], json.loads(snap["metrics"])) is None
        if stale:
            with db.tx() as c:
                c.execute("UPDATE alerts SET ack=1 WHERE id=?", (a["id"],))
            n += 1
    return n


def _sand_alert(cam_id: str, ts: str, result: dict) -> str | None:
    """رمال جديدة على الطريق لم يُنبَّه عليها خلال يوم."""
    if db.one("SELECT id FROM alerts WHERE camera_id=? AND type='sand' AND ts>?",
              (cam_id, (datetime.fromisoformat(ts) - timedelta(days=1)).isoformat())):
        return None
    return _sand_excess(cam_id, ts, result)


def _sand_excess(cam_id: str, ts: str, result: dict) -> str | None:
    """الغطاء الرملي تجاوز خط الأساس (وسيط آخر 5 لقطات في الساعة نفسها تقريبًا) بوضوح.
    الساعة مهمة: ضوء العصر الدافئ يجعل الخرسانة الفاتحة أقرب إلى لون الرمل."""
    now = result.get("sand_cover", 0.0)
    cam = get_camera(cam_id)
    hour = lambda t: datetime.fromisoformat(t).astimezone(tz(cam)).hour if cam else 0  # noqa: E731
    prev = [json.loads(r["metrics"]).get("sand_cover") for r in db.query(
        "SELECT ts, metrics FROM snapshots WHERE camera_id=? AND condition_index IS NOT NULL AND ts<? ORDER BY ts DESC LIMIT 20",
        (cam_id, ts)) if abs(hour(r["ts"]) - hour(ts)) <= 2][:5]
    prev = [p for p in prev if p is not None]
    if len(prev) < 2 or now < 0.10 or now - float(np.median(prev)) < 0.08:
        return None
    return f"رمال على الطريق: تغطي ~{now * 100:.0f}% من السطح (كانت ~{float(np.median(prev)) * 100:.0f}%) — يوصى بإزالتها لسلامة السائقين."


def _analyze(img, roi, prev_img, use_ai=True):
    result = vision.analyze(img, roi, use_ai)
    result["sand_cover"] = gulf.sand_cover(img, roi)
    diff = change.compare(prev_img, img, roi) if prev_img is not None else {"changed_pct": 0.0, "boxes": [], "darker_ratio": 0.0}
    if diff.get("view_changed"):
        return result, diff
    return result, diff


def _suspicious(prev: dict, result: dict, diff: dict) -> bool:
    if diff.get("view_changed"):
        return False
    return ((diff["changed_pct"] >= config.SUDDEN_CHANGE_PCT and diff["darker_ratio"] >= 0.5)
            or result["pothole_count"] > (prev["pothole_count"] or 0)
            or prev["condition_index"] - result["condition_index"] >= config.SUDDEN_CI_DROP)


def store_risk(cam_id: str, ts: str, a: dict) -> None:
    db.insert("risk", {"camera_id": cam_id, "ts": ts, "score": a["score"], "level": a["level"],
                       "prob_90d": a["prob_90d"], "weeks_to_threshold": a["weeks_to_threshold"], "factors": a["factors"],
                       "forecast": {k: a[k] for k in ("forecast", "ci", "ci_slope", "effective_slope", "season_factor", "heat",
                                                      "outlook", "priority", "level_ar", "next_inspection_days", "features", "gulf")},
                       "recommendations": a["recommendations"]})


def backfill_issue_alerts() -> int:
    """مشكلات نشطة بلا تنبيه (فُتحت قبل إصلاح تنبيه «أول تحليل دون العتبة»): يُضاف تنبيهها مرة واحدة."""
    n = 0
    for i in db.query("SELECT * FROM issues WHERE stage='active' AND kind='deterioration'"):
        if db.one("SELECT id FROM alerts WHERE camera_id=? AND type='threshold' AND ts>=?", (i["camera_id"], i["detected_ts"])):
            continue
        cam = get_camera(i["camera_id"])
        if cam:
            add_alert(cam, i["detected_ts"], "threshold", "critical",
                      f"مؤشر الحالة {i['last_ci']:.0f} دون عتبة الصيانة ({config.MAINTENANCE_THRESHOLD:.0f}) — يوصى بفحص ميداني وصيانة تصحيحية.")
            n += 1
    return n


def refresh_risk(max_age: timedelta = timedelta(hours=20)) -> int:
    """تحديث يومي لتقييم المقاطع التي لم تُلتقط اليوم: الطقس وحرارة الرصف وخطر التخدد تتغير ولو لم تتغير الصورة."""
    now = datetime.now(timezone.utc)
    n = 0
    for cam in cameras():
        last = db.one("SELECT ts, forecast FROM risk WHERE camera_id=? ORDER BY ts DESC LIMIT 1", (cam["id"],))
        if last and now - datetime.fromisoformat(last["ts"]) < max_age and '"gulf"' in (last["forecast"] or ""):
            continue  # حديث ويتضمن فيزياء الرصف
        a = assess_camera(cam, now)
        if a:
            store_risk(cam["id"], now.isoformat(timespec="seconds"), a)
            n += 1
    return n


def assess_camera(cam: dict, at: datetime) -> dict | None:
    hist = [h for h in history(cam["id"]) if h["ts"] <= at.isoformat(timespec="seconds")]
    if not hist:
        return None
    region = cam.get("region") or config.REGION_KEYS[0]
    day = at.astimezone(tz(cam)).date()
    heat = weather.heat_features(day, region)
    out = weather.outlook(day + timedelta(days=1), region)
    n_inc = len(incidents.near(cam)) if incidents.enabled() and at > datetime.now(timezone.utc) - timedelta(hours=1) else 0
    try:
        phys = gulf.pavement_features(cam, day)
    except Exception:
        log.exception("gulf features failed for %s", cam["id"])
        phys = None
    return risk.assess(cam, hist, heat, out, n_inc, at.astimezone(tz(cam)), phys)


def check_incidents() -> int:
    """تنبيه فوري عند حادث قريب جدًا من كاميرا خلال آخر ساعتين، مع التقاط فحص سريع."""
    if not incidents.enabled():
        return 0
    n = 0
    for cam in cameras():
        recent = incidents.near(cam, radius_km=0.4, within=timedelta(hours=2))
        if recent and not db.one("SELECT id FROM alerts WHERE camera_id=? AND type='incident' AND ts>?",
                                 (cam["id"], (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())):
            add_alert(cam, datetime.now(timezone.utc).isoformat(timespec="seconds"), "incident", "info",
                      f"{len(recent)} حادث/حوادث خلال 400 م — سيُجرى فحص سريع للقطة الطريق.")
            run_capture(cam["id"], "sentinel")
            n += 1
    return n


def is_daylight(cam: dict, at: datetime | None = None) -> bool:
    h = (at or datetime.now(timezone.utc)).astimezone(tz(cam)).hour
    return config.DAYLIGHT_HOURS[0] <= h < config.DAYLIGHT_HOURS[1]


def catch_up(max_age: timedelta = timedelta(days=7)) -> int:
    """عند تشغيل الخادم: التقاط فوري لأي كاميرا لم تُحلَّل منذ أسبوع (مثل كاميرا حقيقية أضيفت حديثًا
    أو خادم كان متوقفًا وقت الجدول الأسبوعي)."""
    cutoff = (datetime.now(timezone.utc) - max_age).isoformat()
    n = 0
    for cam in cameras():
        if not db.one("SELECT id FROM snapshots WHERE camera_id=? AND ts>? LIMIT 1", (cam["id"], cutoff)):
            if cam["source"].get("type") != "demo" and not is_daylight(cam):
                continue  # ليلًا في منطقة الكاميرا — يلتقطها المجدول في موعدها النهاري
            run_capture(cam["id"], "weekly")
            n += 1
    return n


# ---------- السجل التاريخي التجريبي ----------

def seed_history(weeks: int | None = None, now: datetime | None = None) -> int:
    """للمصادر التي تحتفظ بصورها السابقة (المحاكاة، data.gov.sg): بناء لقطات أسبوعية لعدد من الأسابيع
    الماضية + فحوص يومية لآخر أسبوع، حتى تظهر الاتجاهات والتنبؤات والتنبيهات فور التشغيل الأول.
    مع كاميرات data.gov.sg تكون هذه صورًا حقيقية من الأرشيف لا محاكاة."""
    weeks = config.SEED_WEEKS if weeks is None else weeks
    now_utc = now or datetime.now(timezone.utc)
    demo = [c for c in cameras() if sources.supports_history(c)
            and not db.one("SELECT id FROM snapshots WHERE camera_id=? LIMIT 1", (c["id"],))]
    if not demo or weeks <= 0:
        return 0
    for region in {c["region"] for c in demo}:
        try:  # جلب الطقس للفترة كلها دفعة واحدة لكل منطقة
            weather.daily_range((now_utc - timedelta(weeks=weeks, days=31)).date(), (now_utc + timedelta(days=15)).date(), region)
        except Exception as e:
            log.warning("weather prefetch failed: %s", e)

    def plan_for(cam):
        # الجدول بالتوقيت المحلي للكاميرا: الإثنين في ساعة الالتقاط + فحص يومي ظهرًا لآخر 6 أيام
        now = now_utc.astimezone(tz(cam))
        last_monday = (now - timedelta(days=now.weekday())).replace(hour=config.WEEKLY_HOUR, minute=0, second=0, microsecond=0)
        if last_monday > now:
            last_monday -= timedelta(weeks=1)
        plan = [(last_monday - timedelta(weeks=w), "seed") for w in range(weeks - 1, -1, -1)]
        plan += [(now.replace(hour=11, minute=0, second=0, microsecond=0) - timedelta(days=d), "sentinel")
                 for d in range(6, 0, -1)]
        return sorted(p for p in plan if p[0] < now)

    def seed_one(cam):
        plan = plan_for(cam)
        for at, kind in plan:
            run_capture(cam["id"], kind, at.astimezone(timezone.utc), n_frames=config.SEED_FRAMES, interval=0)
        log.info("seeded %s", cam["id"])
        return len(plan)

    with ThreadPoolExecutor(max_workers=4) as ex:
        return sum(ex.map(seed_one, demo))
