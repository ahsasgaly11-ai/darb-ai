"""كاشف عيوب الطرق بالذكاء الاصطناعي — نماذج YOLO مدرّبة على RDD2022.

RDD2022 مجموعة بيانات دولية لعيوب الطرق (اليابان، الهند، التشيك، النرويج، الولايات المتحدة، الصين)
بفئات: D00 تشقق طولي، D10 عرضي، D20 تمساحي، D40 حفرة (وبعض النماذج تضيف «Repair» للترقيعات).

لماذا التقطيع (Tiling)؟ النماذج دُرّبت على صور من كاميرا السيارة حيث التشقق كبير في الصورة؛ في كاميرات
المرور المرتفعة يصبح التشقق بضعة بكسلات. تقطيع منطقة الطريق إلى بلاطات بالدقة الكاملة وتشغيل النموذج
على كل بلاطة (أسلوب SAHI) يرفع قدرة الاكتشاف كثيرًا.

لماذا التجميع (Ensemble)؟ في اختباراتنا على صور أريزونا وسنغافورة الحقيقية التقط كل نموذج عيوبًا فاتت الآخر،
ولم يُعطِ أيّ منهما إنذارات كاذبة تُذكر على الطرق السليمة؛ فالدمج يرفع الاكتشاف دون كلفة كبيرة.
"""
from __future__ import annotations

import logging
import threading
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from . import config

log = logging.getLogger("darb.ai")

CLASS_MAP = {
    "d00": "crack_long", "longitudinal_crack": "crack_long", "longitudinal crack": "crack_long",
    "d10": "crack_trans", "transverse_crack": "crack_trans", "transverse crack": "crack_trans",
    "d20": "alligator", "alligator_crack": "alligator", "alligator crack": "alligator",
    "d40": "pothole", "pothole": "pothole",
    "repair": "repair",
}
_lock = threading.Lock()  # نماذج PyTorch ليست آمنة للاستدعاء المتوازي على نفس الكائن


def model_paths() -> list[Path]:
    if config.YOLO_MODELS:
        return [Path(p) for p in config.YOLO_MODELS]
    return sorted(config.MODELS_DIR.glob("*.pt"))


@lru_cache(maxsize=1)
def models() -> tuple:
    paths = [p for p in model_paths() if p.exists()]
    if not paths:
        return ()
    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError:
        log.warning("ultralytics غير مثبتة — يُستخدم الكشف الكلاسيكي (pip install -r requirements-ai.txt)")
        return ()
    loaded = []
    for p in paths:
        try:
            loaded.append((p.stem, YOLO(str(p))))
        except Exception as e:
            log.warning("تعذّر تحميل النموذج %s: %s", p, e)
    log.info("AI models: %s", [n for n, _ in loaded])
    return tuple(loaded)


def available() -> bool:
    return bool(models())


def names() -> list[str]:
    return [n for n, _ in models()]


def _tiles(x0: int, y0: int, x1: int, y1: int, tile: int, overlap: float = 0.25):
    step = max(1, int(tile * (1 - overlap)))
    xs = list(range(x0, max(x0 + 1, x1 - tile + 1), step)) or [x0]
    ys = list(range(y0, max(y0 + 1, y1 - tile + 1), step)) or [y0]
    if xs[-1] + tile < x1:
        xs.append(max(x0, x1 - tile))
    if ys[-1] + tile < y1:
        ys.append(max(y0, y1 - tile))
    return [(x, y) for y in ys for x in xs]


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    return inter / max(1e-6, (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter)


def detect(img: np.ndarray, mask: np.ndarray) -> list[dict]:
    """اكتشاف العيوب داخل منطقة الطريق. يعيد قائمة بنفس صيغة الكاشف الكلاسيكي."""
    ms = models()
    if not ms:
        return []
    ys, xs = np.where(mask > 0)
    if xs.size == 0:
        return []
    h, w = img.shape[:2]
    tile = min(config.YOLO_TILE, w, h)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x1, y1 = max(x1, x0 + tile), max(y1, y0 + tile)
    x0, y0 = min(x0, w - tile), min(y0, h - tile)
    offs = _tiles(max(0, x0), max(0, y0), min(w, x1), min(h, y1), tile)
    crops = [img[y:y + tile, x:x + tile] for x, y in offs]

    raw = []  # [x1,y1,x2,y2,type,conf,model]
    with _lock:
        for name, m in ms:
            for res, (ox, oy) in zip(m.predict(crops, imgsz=640, conf=config.YOLO_CONF, verbose=False), offs):
                for (bx1, by1, bx2, by2), c, s in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
                    kind = CLASS_MAP.get(str(res.names[int(c)]).lower())
                    if kind:
                        raw.append([bx1 + ox, by1 + oy, bx2 + ox, by2 + oy, kind, float(s), name])

    # استبعاد: خارج منطقة الطريق، فوق علامات الطريق البيضاء (ممرات المشاة والأسهم)، أو جسم ملوّن
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    road_med = float(np.median(gray[mask > 0]))
    bright = (gray > max(150, road_med * 1.6)).astype(np.uint8)
    sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 1]
    kept = []
    for b in raw:
        bx1, by1, bx2, by2 = (int(max(0, b[0])), int(max(0, b[1])), int(min(w, b[2])), int(min(h, b[3])))
        if bx2 - bx1 < 4 or by2 - by1 < 4:
            continue
        cx, cy = (bx1 + bx2) // 2, (by1 + by2) // 2
        if not mask[cy, cx]:
            continue
        if b[4] != "repair":
            if bright[by1:by2, bx1:bx2].mean() > 0.35 or sat[by1:by2, bx1:bx2].mean() > 80:
                continue
        kept.append(b)

    # دمج: NMS لكل فئة عبر البلاطات والنماذج؛ اتفاق نموذجين على الموضع يرفع الثقة
    kept.sort(key=lambda b: -b[5])
    out: list[list] = []
    for b in kept:
        dup = next((o for o in out if o[4] == b[4] and _iou(o[:4], b[:4]) > 0.35), None)
        if dup is None:
            out.append(b + [{b[6]}])
        else:
            if b[6] not in dup[7]:
                dup[7].add(b[6])
                dup[5] = min(0.99, dup[5] + 0.1 * b[5])
            dup[0], dup[1] = min(dup[0], b[0]), min(dup[1], b[1])
            dup[2], dup[3] = max(dup[2], b[2]), max(dup[3], b[3])
    # الحفرة تطلق تنبيهًا حرجًا: نشترط اتفاق نموذجين أو ثقة عالية (في الصور الحقيقية كانت بقايا
    # دراجة نارية داكنة تُقرأ حفرة من نموذج واحد بثقة منخفضة)
    if len(ms) > 1:
        out = [b for b in out if b[4] != "pothole" or len(b[7]) > 1 or b[5] >= 0.5]
    fill = {"crack_long": 0.22, "crack_trans": 0.22, "alligator": 0.5, "pothole": 0.7, "repair": 0.8}
    return [{
        "type": b[4], "bbox": [int(b[0]), int(b[1]), int(b[2] - b[0]), int(b[3] - b[1])],
        # التشقق يشغل جزءًا من مربعه فقط — المساحة الفعلية تقديرية حسب الفئة
        "area": float((b[2] - b[0]) * (b[3] - b[1]) * fill[b[4]]),
        "confidence": round(b[5], 2), "models": sorted(b[7]),
    } for b in out]
