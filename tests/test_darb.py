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

from backend import app as app_mod, db, pipeline, risk, sources, synthetic, vision  # noqa: E402

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
    assert sources.occlusion(jam, roi) > 0.10


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
    # بعد: إعادة رصف (قفزة كبيرة في المؤشر) → مراقبة
    lifecycle.update(cam, ts(8), res(95), {"ci": 95, "weeks_to_threshold": None, "ci_slope": 0}, noalerts, add)
    i = db.one("SELECT * FROM issues WHERE id=?", (i["id"],))
    assert i["stage"] == "monitoring" and i["resolution"] == "repaired" and "resolved" in calls
    # انتهاء مراقبة ما بعد الإصلاح دون عودة → مغلقة
    lifecycle.update(cam, ts(17), res(94), {"ci": 94, "weeks_to_threshold": None, "ci_slope": 0}, noalerts, add)
    i = db.one("SELECT * FROM issues WHERE id=?", (i["id"],))
    assert i["stage"] == "closed" and i["resolution"] == "repaired"
    k = lifecycle.kpis(["t-life"])
    assert k["avg_lead_weeks"] == 5 and k["avg_days_to_resolve"] == 21 and k["prediction_precision"] == 1.0


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
