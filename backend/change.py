"""كشف التغيّر المفاجئ بين لقطتين للكاميرا نفسها (حفرة جديدة، انهيار، مخلّفات، تجمع مياه...).

يُطبَّع سطوع منطقة الطريق في الصورتين، ثم يُحسب الفرق المطلق وتُستبعد الفروق الصغيرة والضجيج،
وتُعاد نسبة المساحة المتغيرة ومربعات المناطق الجديدة. لا يحتاج تدريبًا، فيلتقط أيضًا
المشاكل غير المألوفة التي لا يعرفها كاشف العيوب.
"""
from __future__ import annotations

import cv2
import numpy as np

from .vision import _normalize, roi_mask


_sift = cv2.SIFT_create(6000)
_clahe = cv2.createCLAHE(2.0, (8, 8))
MIN_INLIERS = 25  # أقل من ذلك قد يكون تطابقًا عرضيًا؛ والكاميرات التي تحرّكت فعلًا بقيت مرفوضة حتى 20 في الاختبار


def _scene_mask(h: int, w: int) -> np.ndarray:
    """يستبعد ما يُطبع فوق الصورة في مكان ثابت (شريط الاسم والوقت، الشعارات في الزوايا): يتطابق دائمًا
    مهما تحرّكت الكاميرا فيُضلّل المحاذاة نحو «لم تتحرك»."""
    m = np.full((h, w), 255, np.uint8)
    m[: int(h * 0.1)] = 0
    m[int(h * 0.9):] = 0
    m[: int(h * 0.3), int(w * 0.78):] = 0
    m[int(h * 0.75):, : int(w * 0.38)] = 0
    return m


def homography(prev: np.ndarray, cur: np.ndarray, width: int = 960) -> tuple[np.ndarray | None, int]:
    """مصفوفة التحويل من إحداثيات prev إلى إحداثيات cur، أو None إذا تغيّر المنظر كليًا.
    كاميرا PTZ تدور وتكبّر حول مركزها، فالتحويل بين لقطتيها Homography دقيقة مهما اختلف عمق المشهد.
    SIFT مع تسوية التباين (CLAHE) أثبت من ORB أمام تغيّر الإضاءة بين لقطتين."""
    if prev.shape[:2] != cur.shape[:2]:
        prev = cv2.resize(prev, (cur.shape[1], cur.shape[0]))
    s = width / cur.shape[1]

    def feats(im):
        g = _clahe.apply(cv2.cvtColor(cv2.resize(im, (width, int(im.shape[0] * s))), cv2.COLOR_BGR2GRAY))
        return _sift.detectAndCompute(g, _scene_mask(*g.shape))

    ka, da = feats(prev)
    kb, db_ = feats(cur)
    if da is None or db_ is None or len(ka) < 10 or len(kb) < 10:
        return None, 0
    pairs = cv2.BFMatcher().knnMatch(da, db_, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.8 * n.distance]
    if len(good) < MIN_INLIERS:
        return None, len(good)
    pa = np.float32([ka[m.queryIdx].pt for m in good]) / s
    pb = np.float32([kb[m.trainIdx].pt for m in good]) / s
    H, mask = cv2.findHomography(pa, pb, cv2.RANSAC, 7.5 / s)
    inliers = int(mask.sum()) if mask is not None else 0
    if H is None or inliers < MIN_INLIERS:
        return None, inliers
    return H, inliers


def register(prev: np.ndarray, cur: np.ndarray) -> tuple[np.ndarray | None, int]:
    """محاذاة اللقطة السابقة مع الحالية لتعويض اهتزاز الكاميرا أو انحرافها البسيط.
    تعيد (الصورة السابقة بعد المحاذاة، عدد النقاط المتطابقة) أو (None, n) إذا تغيّر المنظر كليًا."""
    if prev.shape != cur.shape:
        prev = cv2.resize(prev, (cur.shape[1], cur.shape[0]))
    H, inliers = homography(prev, cur)
    if H is None:
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
