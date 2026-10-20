"""مصادر الكاميرات — محوّلات موحّدة تعيد دفعة إطارات من أي كاميرا.

الأنواع المدعومة:
  demo      محاكاة واقعية (لا تحتاج شبكة) — للتجربة والعروض.
  snapshot  رابط صورة JPEG/PNG يتجدد (أشهر صيغة لكاميرات المرور العامة).
  mjpeg     بث MJPEG عبر HTTP.
  rtsp      كاميرا IP عبر RTSP (يتطلب OpenCV مع FFmpeg).
  hls       بث مباشر m3u8 (يتطلب OpenCV مع FFmpeg).
  az511     كاميرات وزارة النقل في أريزونا (ADOT) عبر AZ511 — صور 1920×1080 تتجدد كل دقيقة تقريبًا.
  caltrans  بث فيديو HLS متصل من وزارة النقل في كاليفورنيا (Caltrans) — 1280×720 إلى 1920×1080، تُلتقط منه إطارات للتحليل.
  madrid    كاميرات بلدية مدريد (بيانات مفتوحة CC BY 4.0) — صور 1920×1080 تتجدد كل 3–15 دقيقة.
  fl511     كاميرات وزارة النقل في فلوريدا (FDOT) عبر FL511 — المنصة نفسها (اختيرت كاميرات 1920×1080 فقط).
  datagovsg كاميرات هيئة النقل البري في سنغافورة (LTA) عبر data.gov.sg — مفتوحة المصدر
            برخصة Singapore Open Data Licence، وتحتفظ بالصور السابقة فيمكن بناء سجل تاريخي فعلي.

كل التقاط يجمع عدة إطارات متباعدة ثم يأخذ الوسيط الزمني لكل بكسل، فتختفي المركبات
العابرة ويبقى سطح الطريق نفسه — وهو ما يحتاجه تحليل العيوب.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import cv2
import httpx
import numpy as np

from . import config, synthetic


class CaptureError(RuntimeError):
    pass


def _decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise CaptureError("تعذّر فك ترميز الصورة")
    return img


def _snapshot(src: dict, n: int, interval: float) -> list[np.ndarray]:
    frames = []
    headers = {"User-Agent": config.USER_AGENT, **src.get("headers", {})}
    with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
        last_hash = None
        for i in range(n):
            r = client.get(src["url"], params={"_": int(time.time() * 1000)} if src.get("cache_bust", True) else None)
            r.raise_for_status()
            h = hash(r.content)
            if h != last_hash:  # بعض الكاميرات تحدّث الصورة كل 30–60 ثانية؛ لا نكرر الإطار نفسه
                frames.append(_decode(r.content))
                last_hash = h
            if i < n - 1:
                time.sleep(interval)
    if not frames:
        raise CaptureError("لم تُستلم أي صورة")
    return frames


def _mjpeg(src: dict, n: int, interval: float) -> list[np.ndarray]:
    frames, buf = [], b""
    next_at = 0.0
    with httpx.stream("GET", src["url"], timeout=30, headers={"User-Agent": config.USER_AGENT}) as r:
        r.raise_for_status()
        for chunk in r.iter_bytes():
            buf += chunk
            a, b = buf.find(b"\xff\xd8"), buf.find(b"\xff\xd9")
            if a != -1 and b != -1 and b > a:
                jpg, buf = buf[a:b + 2], buf[b + 2:]
                if time.time() >= next_at:
                    frames.append(_decode(jpg))
                    next_at = time.time() + interval
                    if len(frames) >= n:
                        break
    return frames


def _video(src: dict, n: int, interval: float) -> list[np.ndarray]:
    cap = cv2.VideoCapture(src["url"])
    if not cap.isOpened():
        raise CaptureError("تعذّر فتح البث (تأكد من دعم FFmpeg في OpenCV)")
    frames, next_at, deadline = [], 0.0, time.time() + n * interval + 60
    try:
        while len(frames) < n and time.time() < deadline:
            ok, f = cap.read()
            if not ok:
                break
            if time.time() >= next_at:
                if f.shape[1] > 1280:  # مثل بقية المصادر: 1280 عرضًا تكفي للتحليل
                    f = cv2.resize(f, (1280, int(f.shape[0] * 1280 / f.shape[1])), interpolation=cv2.INTER_AREA)
                frames.append(f)
                next_at = time.time() + interval
    finally:
        cap.release()
    if not frames:
        raise CaptureError("لم يُقرأ أي إطار من البث")
    return frames


DATAGOVSG_URL = "https://api.data.gov.sg/v1/transport/traffic-images"
_sg_cache: OrderedDict[str, dict] = OrderedDict()  # استجابة واحدة تضم كل الكاميرات — نعيد استخدامها
_sg_lock = threading.Lock()


def _datagovsg_index(at: datetime) -> dict:
    stamp = at.astimezone(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%dT%H:%M:00")
    with _sg_lock:
        if stamp in _sg_cache:
            return _sg_cache[stamp]
    headers = {"User-Agent": config.USER_AGENT}
    if config.DATAGOVSG_API_KEY:
        headers["x-api-key"] = config.DATAGOVSG_API_KEY
    for attempt in range(4):
        r = httpx.get(DATAGOVSG_URL, params={"date_time": stamp}, headers=headers, timeout=30)
        if r.status_code == 429:  # تجاوز حد الطلبات — انتظار متزايد
            time.sleep(2 ** attempt * 2)
            continue
        r.raise_for_status()
        break
    else:
        raise CaptureError("data.gov.sg: تجاوز حد الطلبات")
    items = r.json().get("items") or [{}]
    idx = {c["camera_id"]: c for c in items[0].get("cameras", [])}
    with _sg_lock:
        _sg_cache[stamp] = idx
        while len(_sg_cache) > 256:
            _sg_cache.popitem(last=False)
    return idx


def _datagovsg(src: dict, at: datetime, n: int) -> list[np.ndarray]:
    """إطارات الدفعة من صور الدقائق السابقة للحظة الالتقاط (تتجدد الصور كل 20–60 ثانية)،
    فتعمل الدفعة فورًا للالتقاط الحي والتاريخي على السواء."""
    frames, seen = [], set()
    now = datetime.now(at.tzinfo)
    for k in range(n * 2):
        if len(frames) >= n:
            break
        t = min(at, now) - timedelta(minutes=k)
        cam = _datagovsg_index(t).get(str(src["camera_id"]))
        if not cam or cam["image"] in seen:
            continue
        seen.add(cam["image"])
        r = httpx.get(cam["image"], timeout=30, headers={"User-Agent": config.USER_AGENT})
        r.raise_for_status()
        img = _decode(r.content)
        if img.shape[1] > 1280:  # توحيد الحجم يسرّع التحليل ويقلل التخزين
            img = cv2.resize(img, (1280, int(img.shape[0] * 1280 / img.shape[1])), interpolation=cv2.INTER_AREA)
        frames.append(img)
    if not frames:
        raise CaptureError(f"الكاميرا {src['camera_id']} غير متاحة في data.gov.sg عند {at:%Y-%m-%d %H:%M}")
    h, w = frames[0].shape[:2]
    return [f if f.shape[:2] == (h, w) else cv2.resize(f, (w, h)) for f in frames]


# منصات 511 المتطابقة (الرابط /map/Cctv/{image_id})
BASE_511 = {"az511": "https://az511.gov", "fl511": "https://fl511.com"}


def cctv_url(src: dict) -> str:
    if src["type"] == "madrid":
        return f"https://informo.madrid.es/cameras/Camara{src['image_id']}.jpg"
    return f"{src.get('base', BASE_511[src['type']])}/map/Cctv/{src['image_id']}"


STILL_TYPES = (*BASE_511, "madrid")  # صور ثابتة متجددة: تُجمع الإطارات المختلفة فقط


def _az511(src: dict, n: int, interval: float) -> list[np.ndarray]:
    """صور منصات 511 ومدريد تتجدد كل ~1–3 دقائق: نأخذ الإطارات المختلفة فقط على مدى بضع دقائق
    (5 إطارات مختلفة تكفي للوسيط الزمني؛ المهلة تتسع لها مع تجدد بطيء)."""
    url = cctv_url({"type": "az511", **src})
    label = "مدريد" if src.get("type") == "madrid" else "AZ511"
    headers = {"User-Agent": config.USER_AGENT}
    frames, seen, same, errors = [], set(), 0, 0
    deadline = time.time() + (max(60.0, n * 75.0) if interval else 30.0)
    with httpx.Client(timeout=30, headers=headers, follow_redirects=True) as client:
        # تتوقف الدفعة إذا لم تتجدد الصورة دقيقتين ونصفًا تقريبًا (بعض الكاميرات تتجدد ببطء)
        while len(frames) < n and time.time() < deadline and not (frames and same * max(interval, 1) >= 150):
            r = client.get(url, params={"t": int(time.time())})
            if r.status_code >= 400:
                # رفض عابر من الخادم (يحدث أحيانًا): نكتفي بما وصل، أو نعيد المحاولة مرتين قبل اعتبار الكاميرا متعطلة
                errors += 1
                if frames:
                    break
                if errors >= 3:
                    r.raise_for_status()
                time.sleep(10)
                continue
            if "png" in r.headers.get("content-type", "") or len(r.content) < 20000:
                # صورة بديلة «No live camera feed» — الكاميرا متوقفة
                raise CaptureError(f"الكاميرا غير متصلة حاليًا ({label}: صورة بديلة)")
            h = hash(r.content)
            same = same + 1 if h in seen else 0
            if h not in seen:
                seen.add(h)
                img = _decode(r.content)
                if img.shape[1] > 1280:
                    img = cv2.resize(img, (1280, int(img.shape[0] * 1280 / img.shape[1])), interpolation=cv2.INTER_AREA)
                frames.append(img)
            if len(frames) < n and interval > 0:
                time.sleep(interval)
    if not frames:
        raise CaptureError(f"لم تُستلم صور من {label}")
    return frames


def supports_history(camera: dict) -> bool:
    """مصادر يمكن طلب صورها في لحظة ماضية — تُستخدم لبناء سجل تاريخي عند أول تشغيل."""
    return camera["source"].get("type") in ("demo", "datagovsg")


def capture(camera: dict, at: datetime, n: int | None = None, interval: float | None = None) -> list[np.ndarray]:
    src = camera["source"]
    n = n or config.BURST_FRAMES
    interval = config.BURST_INTERVAL if interval is None else interval
    kind = src.get("type")
    if kind == "demo":
        return synthetic.capture_frames(src, camera.get("meta", {}), at, n)
    if kind == "datagovsg":
        return _datagovsg(src, at, n)
    if kind in STILL_TYPES:
        return _az511(src, n, src.get("burst_interval", 20.0) if interval else 0)
    if kind == "snapshot":
        return _snapshot(src, n, interval)
    if kind == "mjpeg":
        return _mjpeg(src, n, interval)
    if kind in ("rtsp", "hls", "video", "caltrans"):
        return _video(src, n, interval)
    raise CaptureError(f"نوع مصدر غير معروف: {kind}")


def background(frames: list[np.ndarray]) -> np.ndarray:
    """الوسيط الزمني: يزيل المركبات والمشاة ويُبقي الطريق."""
    if len(frames) == 1:
        return frames[0]
    h, w = frames[0].shape[:2]
    stack = np.stack([cv2.resize(f, (w, h)) for f in frames])
    return np.median(stack, axis=0).astype(np.uint8)


def occlusion(frames: list[np.ndarray], roi: list[list[float]]) -> float:
    """نسبة منطقة الطريق التي تحجبها مركبات لا يزيلها الوسيط (ازدحام/توقف): بكسلات تختلف عن الوسيط
    في أكثر من 20% من الإطارات. القيم فوق ~0.10 تعني أن سطح الطريق غير ظاهر بما يكفي للتحليل."""
    if len(frames) < 3:
        return 0.0
    from .vision import roi_mask
    st = np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]).astype(np.int16)
    dev = (np.abs(st - np.median(st, axis=0)) > 30).mean(axis=0)
    m = roi_mask(frames[0].shape, roi) > 0
    return round(float((dev[m] > 0.2).mean()), 3)


def default_roi(camera: dict) -> list[list[float]]:
    roi = camera.get("meta", {}).get("roi")
    if roi:
        return roi
    if camera["source"].get("type") == "demo":
        return synthetic.road_roi()
    # افتراضي لكاميرا مرور نموذجية: الطريق يملأ النصف السفلي بشكل شبه منحرف
    return [[0.03, 0.98], [0.97, 0.98], [0.64, 0.48], [0.36, 0.48]]
