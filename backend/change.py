"""كشف التغيّر المفاجئ بين لقطتين للكاميرا نفسها (حفرة جديدة، انهيار، مخلّفات، تجمع مياه...).

يُطبَّع سطوع منطقة الطريق في الصورتين، ثم يُحسب الفرق المطلق وتُستبعد الفروق الصغيرة والضجيج،
وتُعاد نسبة المساحة المتغيرة ومربعات المناطق الجديدة. لا يحتاج تدريبًا، فيلتقط أيضًا
المشاكل غير المألوفة التي لا يعرفها كاشف العيوب.
"""
from __future__ import annotations

import cv2
import numpy as np

from .vision import _normalize, roi_mask


_orb = cv2.ORB_create(2000)


def register(prev: np.ndarray, cur: np.ndarray) -> tuple[np.ndarray | None, int]:
    """محاذاة اللقطة السابقة مع الحالية (ORB + Homography) لتعويض اهتزاز الكاميرا أو انحرافها البسيط.
    تعيد (الصورة السابقة بعد المحاذاة، عدد النقاط المتطابقة) أو (None, n) إذا تغيّر المنظر كليًا."""
    s = 640 / cur.shape[1]
    small = lambda im: cv2.cvtColor(cv2.resize(im, (640, int(im.shape[0] * s))), cv2.COLOR_BGR2GRAY)  # noqa: E731
    ka, da = _orb.detectAndCompute(small(prev), None)
    kb, db_ = _orb.detectAndCompute(small(cur), None)
    if da is None or db_ is None:
        return None, 0
    m = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(da, db_)
    if len(m) < 20:
        return None, len(m)
    pa = np.float32([ka[x.queryIdx].pt for x in m]) / s
    pb = np.float32([kb[x.trainIdx].pt for x in m]) / s
    H, mask = cv2.findHomography(pa, pb, cv2.RANSAC, 4.0)
    inliers = int(mask.sum()) if mask is not None else 0
    if H is None or inliers < 60:
        return None, inliers
    return cv2.warpPerspective(prev, H, (cur.shape[1], cur.shape[0]), borderMode=cv2.BORDER_REPLICATE), inliers


def compare(prev: np.ndarray, cur: np.ndarray, roi: list[list[float]], align: bool = True) -> dict:
    if prev.shape != cur.shape:
        prev = cv2.resize(prev, (cur.shape[1], cur.shape[0]))
    inliers = None
    if align:
        aligned, inliers = register(prev, cur)
        if aligned is None:
            # المنظر تغيّر (كاميرا PTZ دارت أو كبّرت) — المقارنة غير ذات معنى
            return {"changed_pct": 0.0, "boxes": [], "darker_ratio": 0.0, "view_changed": True, "inliers": inliers}
        prev = aligned
    mask = cv2.erode(roi_mask(cur.shape, roi), np.ones((11, 11), np.uint8))
    a = cv2.GaussianBlur(_normalize(cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY), mask), (5, 5), 0)
    b = cv2.GaussianBlur(_normalize(cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY), mask), (5, 5), 0)
    diff = cv2.absdiff(a, b)
    darker = (a.astype(np.int16) - b.astype(np.int16)) > 0  # عيوب الرصف تظهر أغمق عادةً
    changed = ((diff > 38) & (mask > 0)).astype(np.uint8) * 255
    changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    changed = cv2.dilate(changed, np.ones((7, 7), np.uint8))
    roi_area = float((mask > 0).sum()) or 1.0
    boxes, area = [], 0
    for c in cv2.findContours(changed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        a_ = cv2.contourArea(c)
        if a_ < 250:
            continue
        x, y, w, h = cv2.boundingRect(c)
        boxes.append([int(x), int(y), int(w), int(h)])
        area += a_
    dark_ratio = float((darker & (changed > 0)).sum()) / max(1.0, float((changed > 0).sum()))
    return {"changed_pct": round(100 * area / roi_area, 3), "boxes": boxes, "darker_ratio": round(dark_ratio, 2),
            "view_changed": False, "inliers": inliers}
