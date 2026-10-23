"""اختبارات دَرْب AI: الكشف، التغيّر المفاجئ، نموذج المخاطر، مصدر كاميرا HTTP حقيقي، والواجهة البرمجية."""
import http.server
import json
import os
import socketserver
import tempfile
import threading
from datetime import datetime, timedelta, timezone

TMP = tempfile.mkdtemp(prefix="darb-test-")
# ملف كاميرات فارغ: الاختبارات تضيف كاميراتها (المحاكي) ولا تتصل بكاميرات حقيقية
with open(os.path.join(TMP, "cameras.json"), "w") as _f:
    _f.write('{"cameras": []}')
os.environ.update(DARB_DATA_DIR=TMP, DARB_MODELS_DIR=TMP, DARB_REGIONS="singapore", DARB_CAMERAS_FILE=os.path.join(TMP, "cameras.json"), DARB_SCHEDULER="0", DARB_WEATHER="0", DARB_SEED_WEEKS="0",
                  DARB_CONFIRM_DELAY="0", DARB_BURST_INTERVAL="0")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import app as app_mod, config, db, pipeline, risk, sources, synthetic, vision  # noqa: E402

NOW = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
FAST = {"id": "t-fast", "name": "مقطع اختبار سريع التدهور", "road": "T1", "lat": 25.1, "lng": 55.2,
        "source": {"type": "demo", "seed": 1185, "deterioration_rate": 1.7},
        "meta": {"aadt": 86000, "heavy_vehicle_pct": 28, "surface_date": "2018-09-20"}}


def _add(cam):
    with db.tx() as c:
        c.execute("INSERT OR REPLACE INTO cameras(id,name,road,lat,lng,source,meta) VALUES (?,?,?,?,?,?,?)",
                  (cam["id"], cam["name"], cam["road"], cam["lat"], cam["lng"],
                   json.dumps(cam["source"]), json.dumps(cam["meta"])))


def _analyze_at(cam, at):
    img = sources.background(synthetic.capture_frames(cam["source"], cam["meta"], at, 5))
    return vision.analyze(img, sources.default_roi(cam))


def test_vehicles_removed_by_temporal_median():
    frames = synthetic.capture_frames(FAST["source"], FAST["meta"], NOW, 7)
    clean = synthetic._project(synthetic.render_surface(FAST["source"], FAST["meta"], NOW))
    bg = sources.background(frames)
    # الخلفية الوسيطة أقرب إلى الطريق النظيف من أي إطار مفرد
    err_bg = cv2.absdiff(cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY), cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)).mean()
    err_f = min(cv2.absdiff(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)).mean() for f in frames)
    assert err_bg <= err_f


def test_condition_degrades_over_summer():
    before = _analyze_at(FAST, NOW - timedelta(weeks=26))
    after = _analyze_at(FAST, NOW)
    assert after["condition_index"] < before["condition_index"]
    assert after["crack_count"] > 0


def test_new_road_is_healthy():
    cam = {**FAST, "meta": {**FAST["meta"], "surface_date": "2026-06-01"}}
    r = _analyze_at(cam, NOW)
    assert r["condition_index"] >= 95 and r["pothole_count"] == 0


def test_risk_model_orders_by_condition():
    cam = {"meta": {"aadt": 60000, "heavy_vehicle_pct": 15, "surface_date": "2020-01-01"}}
    heat = {"mean_tmax": 40, "days_above_45": 2, "mean_diurnal_range": 11}
    out = {"mean_tmax": 38, "max_tmax": 42}

    def hist(cis):
        return [{"ts": (NOW - timedelta(weeks=len(cis) - i)).isoformat(), "condition_index": c,
                 "pothole_count": 0, "metrics": {"crack_density": 1.0}} for i, c in enumerate(cis)]
    good = risk.assess(cam, hist([92, 92, 91, 91]), heat, out, at=NOW)
    bad = risk.assess(cam, hist([70, 64, 58, 52]), heat, out, at=NOW)
    assert bad["score"] > good["score"]
    assert bad["ci_slope"] < -1
    assert bad["ci"] == 58  # وسيط آخر 3 لقطات — القفزة المنفردة لا تحرّك التقييم وحدها
    assert bad["weeks_to_threshold"] is not None and bad["weeks_to_threshold"] <= 4
    assert abs(sum(f["share"] for f in bad["factors"]) - 100) < 1
    assert bad["recommendations"]


def test_sudden_pothole_triggers_critical_alert():
    ev_at = (NOW - timedelta(days=2)).isoformat()
    cam = {**FAST, "id": "t-sudden", "meta": {**FAST["meta"], "surface_date": "2025-01-01"},
           "source": {**FAST["source"], "sudden_event": {"kind": "pothole", "at": ev_at}}}
    _add(cam)
    pipeline.run_capture(cam["id"], "weekly", NOW - timedelta(days=7), n_frames=5)
    pipeline.run_capture(cam["id"], "sentinel", NOW - timedelta(days=3), n_frames=5)
    assert not db.query("SELECT * FROM alerts WHERE camera_id=? AND severity='critical'", (cam["id"],))
    r = pipeline.run_capture(cam["id"], "sentinel", NOW - timedelta(days=1), n_frames=5)
    assert r["ok"] and not r["alerts"]  # الاكتشاف الأول اشتباه فقط
    assert json.loads(db.one("SELECT metrics FROM snapshots WHERE id=?", (r["snapshot_id"],))["metrics"])["suspect"]
    r = pipeline.run_capture(cam["id"], "sentinel", NOW - timedelta(hours=2), n_frames=5)
    assert r["ok"]
    types = {a["type"] for a in r["alerts"]}
    assert "sudden_change" in types or "new_pothole" in types
    assert any(a["severity"] == "critical" for a in r["alerts"])


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def camera_server():
    """خادم HTTP محلي يحاكي كاميرا مرور عامة تنشر صورة JPEG."""
    d = tempfile.mkdtemp()
    frame = synthetic.capture_frames(FAST["source"], FAST["meta"], NOW, 1)[0]
    cv2.imwrite(os.path.join(d, "cam.jpg"), frame)
    handler = lambda *a, **k: _Handler(*a, directory=d, **k)  # noqa: E731
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/cam.jpg"
    srv.shutdown()


def test_api_end_to_end_with_http_snapshot_camera(camera_server):
    with TestClient(app_mod.app) as client:
        r = client.post("/api/cameras", json={
            "id": "real-http-cam", "name": "كاميرا HTTP", "road": "اختبار", "lat": 25.2, "lng": 55.3,
            "source": {"type": "snapshot", "url": camera_server},
            "meta": {"aadt": 40000, "heavy_vehicle_pct": 10, "surface_date": "2021-01-01",
                     "roi": synthetic.road_roi()}})
        assert r.status_code == 200, r.text
        assert r.json()["first_capture"]["ok"]

        d = client.get("/api/cameras/real-http-cam").json()
        assert d["source_type"] == "snapshot" and d["risk_detail"]
        sid = d["snapshots"][0]["id"]
        img = client.get(f"/api/snapshots/{sid}/image?annotated=1")
        assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"

        s = client.get("/api/summary").json()
        assert s["cameras"] >= 1 and s["priorities"]
        assert client.get("/api/alerts").status_code == 200
        assert client.post("/api/cameras/real-http-cam/maintenance",
                           json={"date": "2026-10-01", "action": "سد تشققات"}).status_code == 200
        assert pipeline.get_camera("real-http-cam")["meta"]["last_maintenance"] == "2026-10-01"
        assert client.get("/api/export/priorities.csv").status_code == 200
        assert client.get("/").status_code == 200

        bad = client.post("/api/cameras", json={"id": "bad-cam", "name": "x1", "lat": 25.2, "lng": 55.3,
                                                "source": {"type": "snapshot", "url": "file:///etc/passwd"}})
        assert bad.status_code == 400


def test_occlusion_flags_congestion():
    clean = synthetic.capture_frames(FAST["source"], FAST["meta"], NOW, 1)[0]
    roi = synthetic.road_roi()
    assert sources.occlusion([clean.copy() for _ in range(5)], roi) == 0
    rng = np.random.default_rng(3)
    jam = []
    for _ in range(5):  # حركة كثيفة: مركبات تغطي معظم الطريق وتتبدّل مواضعها بين الإطارات
        f = clean.copy()
        for _ in range(40):
            x, y = int(rng.uniform(150, 800)), int(rng.uniform(280, 520))
            cv2.rectangle(f, (x, y), (x + 70, y + 40), tuple(int(v) for v in rng.integers(0, 255, 3)), -1)
        jam.append(f)
    assert sources.occlusion(jam, roi) > config.CONGESTION_OCCLUSION
    moving = [clean.copy() for _ in range(5)]  # مرور متحرك: كل موضع محجوب في إطارين فقط فيستعيده الوسيط
    for i in range(5):
        for k in (i, (i + 1) % 5):
            cv2.rectangle(moving[i], (150 + 130 * k, 300), (260 + 130 * k, 500), (20, 20, 20), -1)
    assert sources.occlusion(moving, roi) < config.CONGESTION_OCCLUSION


def test_smoothing_ignores_single_spike_but_keeps_persistent_drop():
    def h(kind, days_ago, ci):
        return {"ts": (NOW - timedelta(days=days_ago)).isoformat(), "kind": kind, "condition_index": ci}
    spike = [h("weekly", 28, 95), h("weekly", 21, 95), h("weekly", 14, 60), h("weekly", 7, 95), h("weekly", 0, 95)]
    assert risk.smooth(spike)[-1]["condition_index"] == 95
    sudden = [h("weekly", 14, 95), h("weekly", 7, 95), h("sentinel", 2, 50), h("sentinel", 1, 50)]
    assert risk.smooth(sudden)[-1]["condition_index"] == 50


def test_datagovsg_adapter(monkeypatch):
    """محوّل data.gov.sg: يطلب صور الدقائق السابقة ويبني الدفعة دون تكرار الصورة نفسها."""
    frame = synthetic.capture_frames(FAST["source"], FAST["meta"], NOW, 1)[0]
    jpg = cv2.imencode(".jpg", cv2.resize(frame, (1920, 1080)))[1].tobytes()
    calls = []

    def fake_index(at):
        calls.append(at)
        return {"4712": {"camera_id": "4712", "image": f"https://img/{int(at.timestamp()) // 120}.jpg"}}

    class R:
        content = jpg
        def raise_for_status(self):
            pass
    monkeypatch.setattr(sources, "_datagovsg_index", fake_index)
    monkeypatch.setattr(sources.httpx, "get", lambda *a, **k: R())
    frames = sources.capture({"source": {"type": "datagovsg", "camera_id": "4712"}}, NOW, 3)
    assert len(frames) == 3 and frames[0].shape[1] == 1280  # تصغير الصور الكبيرة
    assert len(calls) > 3  # تخطّى الدقائق التي لم تتجدد صورتها


def test_lifecycle_before_during_after():
    """سيناريو كامل: تنبؤ ← تحقق ← إصلاح ← مراقبة ← إغلاق، مع مؤشرات سبق التنبؤ وزمن الإصلاح."""
    from backend import lifecycle
    cam = {**FAST, "id": "t-life"}
    _add(cam)
    noalerts = []
    calls = []
    add = lambda c, ts, t, sev, msg, sid=None: calls.append(t) or {"type": t, "severity": sev, "message": msg}  # noqa: E731
    res = lambda ci, dets=(): {"condition_index": ci, "detections": list(dets), "repairs": []}  # noqa: E731
    t0 = NOW - timedelta(weeks=20)
    ts = lambda w: (t0 + timedelta(weeks=w)).isoformat(timespec="seconds")  # noqa: E731

    # قبل: الاتجاه يتوقع بلوغ العتبة خلال 6 أسابيع
    lifecycle.update(cam, ts(0), res(70), {"ci": 70, "weeks_to_threshold": 6, "ci_slope": -2.5}, noalerts, add)
    i = db.one("SELECT * FROM issues WHERE camera_id='t-life'")
    assert i["stage"] == "predicted" and "predicted" in calls
    # أثناء: المؤشر دون العتبة بعد 5 أسابيع → تحقق التنبؤ
    lifecycle.update(cam, ts(5), res(52), {"ci": 52, "weeks_to_threshold": 0, "ci_slope": -3}, noalerts, add)
    i = db.one("SELECT * FROM issues WHERE id=?", (i["id"],))
    assert i["stage"] == "active" and i["detected_ts"] == ts(5)
    # بعد: إعادة رصف (قفزة كبيرة في المؤشر) — لقطة واحدة لا تكفي (قد تكون صورة متأخرة أو إضاءة منخفضة)
    lifecycle.update(cam, ts(8), res(95), {"ci": 95, "weeks_to_threshold": None, "ci_slope": 0}, noalerts, add)
    i = db.one("SELECT * FROM issues WHERE id=?", (i["id"],))
    assert i["stage"] == "active" and "resolved" not in calls
    # تتأكد في لقطة اليوم التالي → مراقبة
    t1 = (t0 + timedelta(weeks=8, days=1)).isoformat(timespec="seconds")
    lifecycle.update(cam, t1, res(95), {"ci": 95, "weeks_to_threshold": None, "ci_slope": 0}, noalerts, add)
    i = db.one("SELECT * FROM issues WHERE id=?", (i["id"],))
    assert i["stage"] == "monitoring" and i["resolution"] == "repaired" and "resolved" in calls
    # انتهاء مراقبة ما بعد الإصلاح دون عودة → مغلقة
    lifecycle.update(cam, ts(17), res(94), {"ci": 94, "weeks_to_threshold": None, "ci_slope": 0}, noalerts, add)
    i = db.one("SELECT * FROM issues WHERE id=?", (i["id"],))
    assert i["stage"] == "closed" and i["resolution"] == "repaired"
    k = lifecycle.kpis(["t-life"])
    assert k["avg_lead_weeks"] == 5 and abs(k["avg_days_to_resolve"] - 22) < 0.5 and k["prediction_precision"] == 1.0


def test_defect_tracking_across_captures():
    from backend import lifecycle
    _add({**FAST, "id": "t-track"})
    d = lambda x, a=400: {"type": "crack_long", "bbox": [x, 300, 20, 60], "area": a, "confidence": 0.5}  # noqa: E731
    t = lambda w: (NOW + timedelta(weeks=w)).isoformat()  # noqa: E731
    lifecycle.update_tracks("t-track", t(0), [d(100)], [])
    r = lifecycle.update_tracks("t-track", t(1), [d(104, 500)], [])  # نفس العيب منزاح قليلًا وأكبر
    assert len(r["newly_confirmed"]) == 1
    lifecycle.update_tracks("t-track", t(2), [d(102, 650)], [])
    tr = db.loads(db.one("SELECT * FROM tracks WHERE camera_id='t-track'"), "areas")
    assert tr["hits"] == 3 and tr["status"] == "confirmed" and lifecycle.growth(tr) > 0
    lifecycle.update_tracks("t-track", t(3), [], [])
    r = lifecycle.update_tracks("t-track", t(4), [], [{"type": "repair", "bbox": [95, 290, 40, 80]}])
    assert r["gone"] and r["gone"][0]["status"] == "repaired"  # اختفى وظهر مكانه ترقيع


def test_az511_offline_placeholder(monkeypatch):
    class R:
        status_code = 200
        headers = {"content-type": "image/png"}
        content = b"x" * 15000
        def raise_for_status(self):
            pass

    class C:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def get(self, *a, **k):
            return R()
    monkeypatch.setattr(sources.httpx, "Client", C)
    with pytest.raises(sources.CaptureError):
        sources.capture({"source": {"type": "az511", "image_id": 1}}, NOW, 3, 0)


def test_live_sources():
    from backend.app import _live
    assert _live({"type": "az511", "image_id": 741})["url"] == "https://az511.gov/map/Cctv/741"
    assert _live({"type": "datagovsg", "camera_id": 2704}) == {"kind": "datagovsg", "camera_id": "2704", "refresh": 60}
    # روابط يدوية لا تُكشف إلا بتصريح، وبـ https فقط
    assert _live({"type": "snapshot", "url": "https://x/cam.jpg?token=s"}) is None
    assert _live({"type": "mjpeg", "url": "http://x/s", "live": True}) is None
    assert _live({"type": "mjpeg", "url": "https://x/s", "live": True})["kind"] == "mjpeg"
    assert _live({"type": "demo"}) is None
    assert _live({"type": "fl511", "image_id": 4303})["url"] == "https://fl511.com/map/Cctv/4303"
    hls = {"type": "caltrans", "url": "https://wzmedia.dot.ca.gov/D7/CCTV-178.stream/playlist.m3u8"}
    assert _live(hls) == {"kind": "hls", "url": hls["url"], "refresh": 0}
    assert _live({"type": "hls", "url": "https://x/a.m3u8"}) is None


def test_capture_window_and_weekly_median():
    from zoneinfo import ZoneInfo
    from backend import cli

    class P:
        tz = staticmethod(lambda cam: ZoneInfo("America/Phoenix"))

    class Src:
        supports_history = staticmethod(lambda cam: cam["source"]["type"] == "datagovsg")

    live = {"source": {"type": "az511"}}
    at = lambda h: datetime(2026, 10, 20, h, 7, tzinfo=ZoneInfo("America/Phoenix")).astimezone(timezone.utc)
    assert cli.capture_time(live, at(10), P, Src) == at(10)       # داخل نافذة النهار 8–16
    assert cli.capture_time(live, at(17), P, Src) is None          # خارجها
    arch = {"source": {"type": "datagovsg"}}
    assert cli.capture_time(arch, at(15), P, Src).astimezone(ZoneInfo("America/Phoenix")).hour == 10
    # وسيط الأسبوع: يوم شاذ واحد (مبتل/ظل) لا يغيّر نقطة الأسبوع
    days = [{"ts": (NOW - timedelta(days=30 - d)).isoformat(), "condition_index": 40 if d == 2 else 90} for d in range(7)]
    assert all(w["condition_index"] == 90 for w in risk.weekly(days))


def test_daily_plan_retries_until_analyzed():
    """كل تشغيل في نافذة النهار فرصة جديدة: اللقطة المزدحمة تُعاد، والمتعطلة تُترك بعد 3 محاولات، والمحلَّلة لا تُكرر."""
    from zoneinfo import ZoneInfo
    from backend import cli

    class P:
        tz = staticmethod(lambda cam: ZoneInfo("America/Phoenix"))

    class Src:
        supports_history = staticmethod(lambda cam: False)

    cam = {**FAST, "id": "t-retry", "source": {"type": "az511", "image_id": 1}}
    _add(cam)
    now = datetime(2026, 10, 21, 10, 7, tzinfo=ZoneInfo("America/Phoenix")).astimezone(timezone.utc)
    plan = lambda attempts={}: [c["id"] for c, _ in cli.plan_captures([cam], now, P, Src, db, attempts)[0]]
    assert plan() == ["t-retry"]
    db.insert("snapshots", {"camera_id": "t-retry", "ts": now.isoformat(timespec="seconds"), "kind": "sentinel",
                            "image_path": "x.jpg", "quality": "congested", "metrics": {}})
    assert plan() == ["t-retry"]                                   # مزدحمة: تُعاد في التشغيل التالي
    assert plan({cli.day_key(cam, now, P): cli.MAX_TRIES}) == []    # استنفدت محاولات اليوم
    db.insert("snapshots", {"camera_id": "t-retry", "ts": now.isoformat(timespec="seconds"), "kind": "sentinel",
                            "image_path": "x.jpg", "condition_index": 90.0, "metrics": {}})
    assert plan() == []                                            # حُلّلت اليوم
    late = now + timedelta(hours=7)                                # 17:07: خارج النافذة لكن في ضوء النهار
    assert cli.plan_captures([cam], late, P, Src, db, {})[0] == []
    assert [c["id"] for c, _ in cli.plan_captures([cam], late, P, Src, db, {}, force=True)[0]] == ["t-retry"]


def test_roi_follows_ptz_camera():
    """الكاميرا التي حرّكها المشغّل: تُنقل منطقة الطريق إلى المنظر الجديد، والمنظر المختلف كليًا لا يُحلَّل."""
    rng = np.random.default_rng(7)
    scene = np.full((900, 1500, 3), 110, np.uint8)
    for _ in range(400):  # مشهد غني بالمعالم (علامات، حواف، أعمدة)
        x, y, r = int(rng.uniform(0, 1500)), int(rng.uniform(0, 900)), int(rng.uniform(4, 30))
        cv2.circle(scene, (x, y), r, tuple(int(v) for v in rng.integers(0, 255, 3)), -1)
    view = lambda dx: cv2.resize(scene[100:820, 100 + dx:1380 + dx], (1280, 720))  # noqa: E731
    cam = {**FAST, "id": "t-ptz", "source": {"type": "az511", "image_id": 2},
           "meta": {**FAST["meta"], "roi": [[0.3, 0.5], [0.7, 0.5], [0.8, 0.9], [0.2, 0.9]]}}
    assert pipeline.roi_for_view(cam, view(0)) == (cam["meta"]["roi"], "new")
    pipeline.remember_view(cam, view(0), cam["meta"]["roi"])
    assert pipeline.roi_for_view(cam, view(0))[1] == "same"
    roi, state = pipeline.roi_for_view(cam, view(100))             # دوران أفقي: المشهد انزاح 100 بكسل يسارًا
    assert state == "moved" and abs(roi[0][0] - (0.3 - 100 / 1280)) < 0.01 and abs(roi[0][1] - 0.5) < 0.01
    other = np.full((720, 1280, 3), 90, np.uint8)
    for _ in range(300):
        cv2.rectangle(other, tuple(int(v) for v in rng.uniform(0, 1200, 2)), tuple(int(v) for v in rng.uniform(0, 1280, 2)),
                      tuple(int(v) for v in rng.integers(0, 255, 3)), 2)
    assert pipeline.roi_for_view(cam, other)[1] == "lost"
    # التنبيه «الكاميرا حُرّكت» فقط إذا تكرر في يومين
    _add(cam)
    today = datetime(2026, 10, 22, 17, tzinfo=timezone.utc)
    assert not pipeline._view_lost_persists(cam, today.isoformat())
    db.insert("snapshots", {"camera_id": "t-ptz", "ts": (today - timedelta(days=1)).isoformat(), "kind": "sentinel",
                            "image_path": "x.jpg", "quality": "view_lost", "metrics": {}})
    assert pipeline._view_lost_persists(cam, today.isoformat())


def test_stale_overlay_clock(monkeypatch):
    """صورة ADOT متجمدة: ساعتها المطبوعة متأخرة ساعات عن الوقت المحلي ⇐ تُرفض؛ وغياب Tesseract لا يرفض شيئًا."""
    import shutil
    from zoneinfo import ZoneInfo
    img = np.full((720, 1280, 3), 120, np.uint8)
    cv2.rectangle(img, (950, 15), (1270, 55), (20, 20, 20), -1)
    cv2.putText(img, "10/23/2026 06:44:58", (960, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2)
    now = datetime(2026, 10, 23, 13, 49, tzinfo=ZoneInfo("America/Phoenix"))
    if shutil.which("tesseract"):
        lag = sources.overlay_lag(img, "America/Phoenix", now)
        assert lag is not None and 400 < lag < 430
        assert abs(sources.overlay_lag(img, "America/Phoenix", now.replace(hour=6, minute=46))) < 5
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert sources.overlay_lag(img, "America/Phoenix", now) is None


def test_gulf_pavement_physics():
    from datetime import date as _date
    from backend import gulf
    # الدوحة 46°م: الرصف ~68°م ويحتاج PG 76 (الدرجة المعتمدة في الخليج)؛ سنغافورة 31°م تكفيها PG 58
    assert 66 <= gulf.pavement_max(46, 25.3) <= 70
    assert gulf.pg_required(gulf.pavement_max(48, 25.3)) == 76
    assert gulf.pg_required(gulf.pavement_max(31, 1.35)) == 58
    # الغيوم/الغبار تخفض الفرق بين الرصف والهواء
    d = _date(2026, 7, 1)
    assert gulf.pavement_max(40, 33, radiation=10, day=d) < gulf.pavement_max(40, 33, radiation=30, day=d)
    # الرمال: بيج داخل منطقة الطريق، والإسفلت الرمادي والعلامات الصفراء لا تُحتسب
    img = np.full((100, 200, 3), 90, np.uint8)
    img[60:100, :100] = (120, 180, 215)   # رمل (BGR بيج)
    img[60:100, 100:120] = (0, 210, 240)  # علامة صفراء مشبعة
    roi = [[0, 0.6], [1, 0.6], [1, 1], [0, 1]]
    assert 0.45 <= gulf.sand_cover(img, roi) <= 0.55


def test_gulf_rutting_and_events(monkeypatch):
    from datetime import date as _date
    from backend import gulf, weather
    hot = [{"date": (_date(2026, 7, 31) - timedelta(days=29 - i)).isoformat(), "tmax": 46, "tmin": 32,
            "source": "open-meteo", "precip": 30 if i == 29 else 0, "gust": 70 if i == 28 else 20} for i in range(37)]
    monkeypatch.setattr(weather, "daily_range", lambda s, e, r: [x for x in hot if s.isoformat() <= x["date"] <= e.isoformat()])
    cam = {"region": "phoenix", "meta": {"aadt": 150000, "heavy_vehicle_pct": 12, "binder_pg": 64}}
    f = gulf.pavement_features(cam, _date(2026, 7, 31))
    assert f["pavement_t7max"] > 60 and f["pg_needed_now"] == 70 and f["rutting_level"] == "high"
    assert f["pg_deficit_grades"] >= 1
    assert {e["kind"] for e in f["events"]} == {"flood", "wind"}
    mild = gulf.pavement_features({"region": "phoenix", "meta": {"aadt": 20000, "heavy_vehicle_pct": 5, "binder_pg": 76}},
                                  _date(2026, 7, 31))
    assert mild["rutting_risk"] < f["rutting_risk"]


def test_economics_deferral_and_budget_plan():
    from backend import economics
    cam = {"id": "x", "name": "x", "meta": {"aadt": 120000, "segment_length_m": 500}, "last_snapshot": {"pothole_count": 0}}
    risk_ = lambda ci, slope: {"score": 40, "level": "medium", "forecast": {"ci": ci, "effective_slope": slope}}
    good = economics.analyze(cam, risk_(78, -0.4))      # وقائي الآن، وبعد سنة يحتاج كشطًا (≈57)
    assert good["treatment_now"]["key"] == "preventive" and good["treatment_later"]["key"] == "thin_overlay"
    assert good["deferral_saving"] > good["cost_now"]   # التأجيل يضاعف الكلفة
    bad = economics.analyze({**cam, "id": "y"}, risk_(45, -0.2))
    stable = economics.analyze({**cam, "id": "z"}, risk_(80, 0.0))
    p = economics.plan([good, bad, stable], budget=good["cost_now"] + 1)
    assert [x["camera_id"] for x in p["selected"]] == ["x"]  # الأعلى عائدًا لكل دولار أولًا
    must = economics.analyze({**cam, "id": "m", "last_snapshot": {"pothole_count": 2}}, risk_(80, 0.0))
    assert economics.plan([good, must], budget=must["cost_now"] + 1)["selected"][0]["camera_id"] == "m"  # الحفر أولًا للسلامة


def test_assistant_server_mode(monkeypatch):
    """وضع الخادم: يرسل السياق المضغوط إلى Claude ويعيد النص، ويتعامل مع الرفض (دون مفتاح حقيقي)."""
    import anthropic
    from types import SimpleNamespace
    from backend import assistant
    sent = {}

    class FakeMessages:
        def create(self, **kw):
            sent.update(kw)
            reply = sent.get("_stop", "end_turn")
            return SimpleNamespace(stop_reason=reply, model=kw["model"],
                                   content=[SimpleNamespace(type="text", text="أسوأ مقطع: X")])

    monkeypatch.setattr(anthropic, "Anthropic", lambda: SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages())))
    ctx = assistant.context_for([{"id": "a", "name": "X", "risk": {"score": 80, "ci": 40}, "last_snapshot": {"pothole_count": 1}}],
                                [{"camera_id": "a", "cost_now": 1000, "treatment_now": {"name": "كشط"}}], {}, {"SAR": {"rate": 3.75}}, [])
    out = assistant.ask("ما أسوأ طريق؟", ctx)
    assert out == {"ok": True, "answer": "أسوأ مقطع: X", "model": assistant.MODEL}
    assert sent["fallbacks"] == "default" and "X" in sent["messages"][0]["content"] and "ما أسوأ طريق؟" in sent["messages"][0]["content"]
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert assistant.available() is False


def test_field_reports_roughness_and_github_parse():
    from backend import field
    c = TestClient(app_mod.app)
    db.insert("cameras", {"id": "fld-cam", "name": "مقطع ميداني", "road": "R1", "lat": 1.3000, "lng": 103.8000,
                          "source": json.dumps({"type": "demo"}), "meta": "{}", "enabled": 1, "region": "singapore"})
    # بلاغ مواطن بصورة فيها حفرة داكنة على إسفلت (المحرك الكلاسيكي في الاختبار) على بعد ~110 م من الكاميرا
    img = np.full((720, 1280, 3), 105, np.uint8)
    cv2.ellipse(img, (640, 560), (90, 45), 0, 0, 360, (25, 25, 25), -1)
    url = "data:image/jpeg;base64," + __import__("base64").b64encode(cv2.imencode(".jpg", img)[1]).decode()
    r = c.post("/api/reports", json={"lat": 1.3010, "lng": 103.8000, "kind": "pothole", "note": "حفرة عميقة", "image": url})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["camera_id"] == "fld-cam" and 90 <= out["distance_m"] <= 130 and out["status"] in ("verified", "review")
    lst = c.get("/api/reports").json()
    assert lst[0]["kind_ar"] == "حفرة" and lst[0]["has_image"] and "image_path" not in lst[0]
    assert c.get(f"/api/reports/{out['id']}/image").status_code == 200
    assert c.post("/api/reports", json={"lat": 1.3, "lng": 103.8, "source": "fleet"}).status_code in (200, 401)  # الأسطول برمز المشرف إن وُجد
    assert c.post("/api/reports", json={"lat": 200, "lng": 0}).status_code == 400
    # الخشونة: الاهتزاز الأعلى = IRI أعلى؛ القراءات البطيئة تُهمل؛ وسيط الخلية
    assert field.iri_estimate(2.0, 20) > field.iri_estimate(0.5, 20) and field.iri_estimate(1.0, 30) < field.iri_estimate(1.0, 10)
    pts = [{"lat": 1.3001, "lng": 103.8001, "rms": 1.5, "speed": 20}] * 5 + [{"lat": 1.3001, "lng": 103.8001, "rms": 3, "speed": 2}]
    assert c.post("/api/roughness", json={"device": "t1", "points": pts}).json() == {"accepted": 5}
    cells = c.get("/api/roughness").json()
    assert len(cells) == 1 and cells[0]["n"] == 5 and cells[0]["class"] in ("good", "fair")
    # بلاغ GitHub: العنوان «[بلاغ]» + سطر الموقع + صورة مرفقة
    issue = {"number": 7, "title": "[بلاغ] حفرة", "created_at": "2026-10-20T10:00:00Z",
             "body": "النوع: حفرة\nالموقع: 25.2854, 51.5310\nالملاحظة: أمام المدرسة\n![صورة](https://github.com/user-attachments/assets/abc.jpg)"}
    p = field.parse_issue(issue)
    assert p == {"lat": 25.2854, "lng": 51.531, "kind": "pothole", "image_url": "https://github.com/user-attachments/assets/abc.jpg",
                 "note": "أمام المدرسة", "ref": "7", "ts": "2026-10-20T10:00:00Z"}
    assert field.parse_issue({**issue, "title": "سؤال عام"}) is None


def test_first_analysis_below_threshold_raises_alert():
    """مقطع يُحلَّل أول مرة وهو دون العتبة أصلًا: تُفتح مشكلة نشطة ومعها تنبيه حرج (لا عبور سابق للعتبة)."""
    from backend import lifecycle
    cam = {"id": "thr-cam", "name": "مقطع متدهور", "road": "X", "lat": 1.31, "lng": 103.81, "source": {"type": "demo"}, "meta": {}}
    _add(cam)
    sent = []
    add = lambda c, ts, typ, sev, msg, sid=None: sent.append((typ, sev)) or {"type": typ, "severity": sev, "message": msg}
    result = {"detections": [], "repairs": [], "condition_index": 42.0, "pothole_count": 0}
    lifecycle.update(cam, NOW.isoformat(), result, {"ci": 42.0, "weeks_to_threshold": 0.0, "ci_slope": 0.0}, [], add)
    assert ("threshold", "critical") in sent
    assert db.one("SELECT stage FROM issues WHERE camera_id='thr-cam'")["stage"] == "active"
    # تشغيل لاحق لا يكرر التنبيه، والتعويض لا يضيف تنبيهًا لمشكلة لها تنبيه
    sent.clear()
    lifecycle.update(cam, (NOW + timedelta(days=1)).isoformat(), result, {"ci": 41.0, "weeks_to_threshold": 0.0, "ci_slope": 0.0}, [], add)
    assert sent == []
