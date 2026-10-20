"""تصدير نسخة عرض ثابتة من دَرْب AI: بيانات الواجهة البرمجية + الصور + بلاطات الخريطة كملفات JSON.

    DARB_REGIONS=singapore,phoenix,tucson,yuma,tampa,losangeles,sandiego,madrid python tools/export_static.py site/
    python tools/build_static.py site/ leaflet.css     # leaflet.css من unpkg.com/leaflet@1.9.4/dist/leaflet.css
ثم انشر site/index.html مع site/data/*.json على أي استضافة ثابتة.
"""
import base64
import json
import math
import os
import sys
import time
from pathlib import Path

import cv2
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

from backend import app as app_mod, config, db  # noqa: E402

OUT = Path(sys.argv[1])
(OUT / "data").mkdir(parents=True, exist_ok=True)
client = TestClient(app_mod.app)  # بلا lifespan: لا بذر ولا مجدول
K = 8  # لقطات الخط الزمني المضمّنة لكل كاميرا
K_HI = int(os.getenv("DARB_HI_SNAPSHOTS", "3"))  # أحدث لقطات كل كاميرا تُنشر أيضًا بدقتها الكاملة لعارض التكبير


def get(path):
    r = client.get(path)
    r.raise_for_status()
    return r.json()


def save(name, obj):
    (OUT / "data" / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def img_uri(sid, annotated, width):
    s = db.one("SELECT image_path, annotated_path FROM snapshots WHERE id=?", (sid,))
    rel = s["annotated_path"] if annotated and s["annotated_path"] else s["image_path"]
    im = cv2.imread(str(config.DATA_DIR / rel))
    if im is None:
        return None
    im = cv2.resize(im, (width, int(im.shape[0] * width / im.shape[1])), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 68])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


def write_hi(sid) -> bool:
    """نسخة بالدقة الكاملة (1280) ملفًا مستقلًا: تُحمَّل فقط عند فتح عارض التكبير."""
    s = db.one("SELECT image_path, annotated_path FROM snapshots WHERE id=?", (sid,))
    for ann, rel in ((1, s["annotated_path"] or s["image_path"]), (0, s["image_path"])):
        im = cv2.imread(str(config.DATA_DIR / rel))
        if im is None:
            return False
        cv2.imwrite(str(OUT / "img" / f"{sid}_{ann}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 84])
    return True


(OUT / "img").mkdir(exist_ok=True)
status = get("/api/status")
status["static_snapshot"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
save("status.json", status)
for r in [""] + config.REGION_KEYS:
    q = f"?region={r}" if r else ""
    tag = r or "all"
    save(f"summary_{tag}.json", get("/api/summary" + q))
    save(f"cameras_{tag}.json", get("/api/cameras" + q))
    save(f"issues_{tag}.json", get("/api/issues" + q))
save("alerts.json", get("/api/alerts?limit=300"))

thumbs, hi_all = {}, set()
cams = get("/api/cameras")
for c in cams:
    d = get(f"/api/cameras/{c['id']}")
    ok = [s for s in d["snapshots"] if s["quality"] == "ok"][:K]  # الأحدث أولًا
    d["snapshots"] = ok
    images = {}
    for s in ok:
        images[f"{s['id']}:1"] = img_uri(s["id"], True, 720)
        images[f"{s['id']}:0"] = img_uri(s["id"], False, 720)
    d["_images"] = {k: v for k, v in images.items() if v}
    d["snapshots"] = [x for x in ok if f"{x['id']}:1" in d["_images"]]  # الصور الأقدم قد تكون حُذفت لتوفير المساحة
    d["_hi"] = [x["id"] for x in d["snapshots"][:K_HI] if write_hi(x["id"])]
    hi_all.update(d["_hi"])
    save(f"cam_{c['id']}.json", d)
    if c["last_snapshot"]:
        sid = c["last_snapshot"]["id"]
        thumbs[f"{sid}:1"] = d["_images"].get(f"{sid}:1") or img_uri(sid, True, 720)
        thumbs[f"{sid}:0"] = d["_images"].get(f"{sid}:0") or img_uri(sid, False, 720)
save("thumbs.json", {**{k: v for k, v in thumbs.items() if v}, "_hi": sorted(hi_all)})

# ---------- بلاطات الخريطة (OpenStreetMap) لمناطق الكاميرات فقط ----------
def tile_xy(lat, lng, z):
    n = 2 ** z
    x = int((lng + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


wanted = set()
for z in range(1, 4):  # عرض العالم لـ«كل المناطق»
    for x in range(2 ** z):
        for y in range(2 ** z):
            wanted.add((z, x, y))
for r in config.REGION_KEYS:
    rc = [c for c in cams if c["region"] == r]
    if not rc:
        continue
    lats, lngs = [c["lat"] for c in rc], [c["lng"] for c in rc]
    pad_la, pad_ln = max(0.05, (max(lats) - min(lats)) * 0.35), max(0.05, (max(lngs) - min(lngs)) * 0.35)
    for z in range(4, 13):
        x0, y0 = tile_xy(max(lats) + pad_la, min(lngs) - pad_ln, z)
        x1, y1 = tile_xy(min(lats) - pad_la, max(lngs) + pad_ln, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                wanted.add((z, x, y))
# ذاكرة مؤقتة للبلاطات: تُنزَّل مرة واحدة فقط (احترامًا لسياسة استخدام خوادم OpenStreetMap)
cache_path = config.DATA_DIR / "tiles_cache.json"
tiles = json.loads(cache_path.read_text()) if cache_path.exists() else {}
missing = sorted(t for t in wanted if f"{t[0]}/{t[1]}/{t[2]}" not in tiles)
print("tiles", len(wanted), "to download", len(missing))
with httpx.Client(headers={"User-Agent": "DARB-AI/1.0 static snapshot (research prototype)"}, timeout=30) as hc:
    for z, x, y in missing:
        r = hc.get(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        if r.status_code == 200:
            tiles[f"{z}/{x}/{y}"] = "data:image/png;base64," + base64.b64encode(r.content).decode()
        time.sleep(0.05)
if missing:
    cache_path.write_text(json.dumps(tiles))
save("tiles.json", {k: v for k, v in tiles.items() if tuple(int(p) for p in k.split("/")) in wanted})
total = sum(f.stat().st_size for f in (OUT / "data").iterdir())
print("files", len(list((OUT / "data").iterdir())), "MB", round(total / 1e6, 1))
