"""الرؤية الحاسوبية: كشف عيوب الرصف وقياسها في صورة الطريق.

مساران:
  1) الذكاء الاصطناعي (افتراضي عند توفر النماذج): تجميع نماذج YOLO مدرّبة على RDD2022 مع تقطيع الصورة
     — انظر ai.py. يُنزَّل بـ python -m backend.models.
  2) رؤية كلاسيكية (احتياطي، بلا تدريب، وللمحاكاة): تحويل Black-Hat لإبراز الخطوط الداكنة الرفيعة
     (التشققات)، وعتبة داكنة نسبية مع فلترة الشكل لاكتشاف الحفر، داخل منطقة الطريق فقط.

الناتج مقاييس موحّدة يعتمد عليها نموذج المخاطر، ومؤشر حالة 0–100 على غرار PCI.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from . import ai

log = logging.getLogger("darb.vision")

LABELS_AR = {
    "crack_long": "تشقق طولي",
    "crack_trans": "تشقق عرضي",
    "alligator": "تشقق تمساحي (شبكي)",
    "pothole": "حفرة",
    "repair": "ترقيع/إصلاح سابق",
}


def roi_mask(shape, roi: list[list[float]]) -> np.ndarray:
    h, w = shape[:2]
    poly = np.array([[int(x * w), int(y * h)] for x, y in roi], np.int32)
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [poly], 255)
    return m


def quality(img: np.ndarray) -> dict:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    brightness = float(g.mean())
    sharp = float(cv2.Laplacian(g, cv2.CV_64F).var())
    status = "ok"
    if brightness < 45:
        status = "low_light"
    elif sharp < 25:
        status = "blurry"
    return {"status": status, "brightness": round(brightness, 1), "sharpness": round(sharp, 1)}


def _normalize(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """توحيد الإضاءة داخل منطقة الطريق حتى تتقارن اللقطات عبر الأسابيع."""
    vals = gray[mask > 0]
    med = float(np.median(vals)) if vals.size else 128.0
    out = gray.astype(np.float32) * (110.0 / max(med, 1.0))
    return np.clip(out, 0, 255).astype(np.uint8)


def _classic(img: np.ndarray, mask: np.ndarray) -> list[dict]:
    gray = _normalize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), mask)
    road = cv2.erode(mask, np.ones((9, 9), np.uint8))
    h, w = gray.shape
    scale = w / 960.0
    dets: list[dict] = []

    # --- الحفر: مناطق داكنة جدًا مقارنة بوسيط الطريق، مكتنزة الشكل
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    med = float(np.median(blur[road > 0])) if road.any() else 110
    dark = ((blur < med * 0.42) & (road > 0)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    pothole_mask = np.zeros_like(dark)
    for c in cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        area = cv2.contourArea(c)
        if area < 120 * scale * scale:
            continue
        hull = cv2.contourArea(cv2.convexHull(c)) or 1
        x, y, bw, bh = cv2.boundingRect(c)
        if area / hull > 0.55 and max(bw, bh) / max(1, min(bw, bh)) < 4.5:
            cv2.drawContours(pothole_mask, [c], -1, 255, -1)
            dets.append({"type": "pothole", "bbox": [x, y, bw, bh], "area": float(area),
                         "confidence": round(min(0.95, 0.55 + area / (4000 * scale * scale)), 2)})

    # --- التشققات: Black-Hat يبرز الخطوط الداكنة الرفيعة على خلفية أفتح
    k = max(9, int(15 * scale) | 1)
    bh_img = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    vals = bh_img[road > 0]
    # عتبة متينة: الوسيط + 6×MAD (لا تتأثر بكثرة التشققات نفسها)، بحدّ أدنى ثابت
    if vals.size:
        med_bh = float(np.median(vals))
        mad = float(np.median(np.abs(vals - med_bh))) * 1.4826
        thr = max(34.0, med_bh + 6 * mad)
    else:
        thr = 34.0
    # علامات الطريق البيضاء (أسهم، خطوط متقطعة) تولّد استجابات زائفة على حوافها وفي الفجوات بينها —
    # نستبعد محيطها قبل البحث عن التشققات
    markings = ((blur > med * 1.45) & (road > 0)).astype(np.uint8) * 255
    markings = cv2.dilate(markings, np.ones((k, k), np.uint8))
    crack = ((bh_img > thr) & (road > 0) & (markings == 0)
             & (cv2.dilate(pothole_mask, np.ones((15, 15), np.uint8)) == 0))
    crack = crack.astype(np.uint8) * 255
    crack = cv2.morphologyEx(crack, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # التشقق رمادي دائمًا؛ المكوّنات الملوّنة غالبًا مركبات متوقفة أو حواجز أو أقماع
    sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 1]
    n, labels, stats, _ = cv2.connectedComponentsWithStats(crack, 8)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if float(sat[y:y + bh, x:x + bw].mean()) > 70:
            continue
        span = max(bw, bh)
        if area < 40 * scale or span < 25 * scale:
            continue  # ضجيج أو حبيبات
        fill = area / float(bw * bh)
        if fill > 0.45 and span < 60 * scale:
            continue  # بقعة لا خط
        if fill > 0.12 and span > 90 * scale:
            kind = "alligator"
        elif bw > bh * 1.6:
            kind = "crack_trans"
        elif bh > bw * 1.2:
            kind = "crack_long"
        else:
            kind = "alligator" if fill > 0.12 else ("crack_trans" if bw >= bh else "crack_long")
        dets.append({"type": kind, "bbox": [int(x), int(y), int(bw), int(bh)], "area": float(area),
                     "confidence": round(min(0.9, 0.45 + span / (400 * scale)), 2)})
    return dets


def engine_name(use_ai: bool = True) -> str:
    return f"ai-ensemble({len(ai.names())})" if use_ai and ai.available() else "classic-cv"


def analyze(img: np.ndarray, roi: list[list[float]], use_ai: bool = True) -> dict:
    mask = roi_mask(img.shape, roi)
    use_ai = use_ai and ai.available()
    all_dets = ai.detect(img, mask) if use_ai else _classic(img, mask)
    repairs = [d for d in all_dets if d["type"] == "repair"]
    dets = [d for d in all_dets if d["type"] != "repair"]
    roi_area = float(mask.sum() / 255) or 1.0
    # يعطي الإسقاط المنظوري أسفل الصورة مساحة أكبر؛ نعوّض بوزن العمق لتقريب المساحة الحقيقية
    h = img.shape[0]
    def depth_w(d):
        y = d["bbox"][1] + d["bbox"][3] / 2
        return float(np.clip((h * 0.98 - h * 0.45) / max(y - h * 0.40, 30), 0.8, 3.0))

    cracks = [d for d in dets if d["type"] != "pothole"]
    potholes = [d for d in dets if d["type"] == "pothole"]
    if use_ai:
        # مربعات النموذج تتداخل وتختلف أحجامها حسب زاوية الكاميرا: نقيس المساحة المتأثرة فعلًا
        # (اتحاد المربعات داخل منطقة الطريق) مضروبة بنسبة إشغال العيب لمربعه
        def coverage(ds):
            if not ds:
                return 0.0
            cov = np.zeros(mask.shape, np.float32)
            for d in ds:
                x, y, bw, bh = d["bbox"]
                cov[y:y + bh, x:x + bw] = np.maximum(cov[y:y + bh, x:x + bw], d["area"] / max(1, bw * bh))
            return 100 * float(cov[mask > 0].sum()) / roi_area
        crack_density = coverage(cracks)
        alligator = coverage([d for d in cracks if d["type"] == "alligator"])
        pothole_area = coverage(potholes)
    else:
        crack_density = 100 * sum(d["area"] * depth_w(d) for d in cracks) / roi_area
        alligator = 100 * sum(d["area"] * depth_w(d) for d in cracks if d["type"] == "alligator") / roi_area
        pothole_area = 100 * sum(d["area"] * depth_w(d) for d in potholes) / roi_area

    # مؤشر الحالة (0–100، الأعلى أفضل) — خصومات مستوحاة من منهجية PCI (ASTM D6433)
    if use_ai:
        # منحنيات خصم مشبعة على غرار ASTM D6433: لكل نوع عيب سقف خصم، ويتباطأ الخصم مع ازدياد الكثافة
        linear = max(0.0, crack_density - alligator)
        deduct = (45 * (1 - np.exp(-linear / 6)) + 75 * (1 - np.exp(-alligator / 15))
                  + 80 * (1 - np.exp(-(pothole_area + 0.8 * len(potholes)) / 1.5)))
        ci = float(np.clip(100 - deduct, 0, 100))
    else:
        deduct = 6.0 * crack_density + 6.0 * alligator + 10.0 * pothole_area + 4.0 * len(potholes)
        ci = float(np.clip(100 * np.exp(-deduct / 70), 0, 100))  # تناقص أُسّي: العيوب الأولى تُخصم أكثر نسبيًا
    return {
        "engine": engine_name(use_ai),
        "detections": dets,
        "repairs": repairs,
        "crack_density": round(crack_density, 3),
        "alligator_density": round(alligator, 3),
        "pothole_count": len(potholes),
        "pothole_area_pct": round(pothole_area, 3),
        "crack_count": len(cracks),
        "condition_index": round(ci, 1),
        "by_type": {k: sum(1 for d in all_dets if d["type"] == k) for k in LABELS_AR},
    }


COLORS = {"crack_long": (0, 200, 255), "crack_trans": (0, 140, 255), "alligator": (0, 60, 255), "pothole": (60, 0, 230),
          "repair": (80, 200, 80)}


def annotate(img: np.ndarray, result: dict, roi: list[list[float]], changed: list[list[int]] | None = None) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    poly = np.array([[int(x * w), int(y * h)] for x, y in roi], np.int32)
    cv2.polylines(out, [poly], True, (120, 255, 120), 1, cv2.LINE_AA)
    for bx in changed or []:
        x, y, bw, bh = bx
        cv2.rectangle(out, (x - 4, y - 4), (x + bw + 4, y + bh + 4), (255, 0, 255), 2)
    for d in result["detections"] + result.get("repairs", []):
        x, y, bw, bh = d["bbox"]
        c = COLORS.get(d["type"], (255, 255, 255))
        cv2.rectangle(out, (x, y), (x + bw, y + bh), c, 2)
        cv2.putText(out, d["type"].replace("crack_", ""), (x, max(12, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, c, 1, cv2.LINE_AA)
    cv2.rectangle(out, (0, 0), (w, 26), (20, 20, 20), -1)
    txt = f"CI {result['condition_index']:.0f} | cracks {result['crack_count']} | potholes {result['pothole_count']} | {result['engine']}"
    cv2.putText(out, txt, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return out
