"""مولّد صور طرق محاكاة — يُستخدم في الاختبارات الآلية فقط (مصدر type=demo).

يحاكي منظر كاميرا مرور فوق طريق إسفلتي، ويتدهور الرصف مع الزمن وفق إجهاد حراري ومروري
تراكمي (صيف دبي يسرّع التشقق، والشاحنات الثقيلة تضاعفه)، مع مركبات عابرة وتغيّر إضاءة
بين اللقطات. الصورة حتمية لكل (كاميرا، لحظة)، فيمكن إعادة إنتاج أي لقطة تاريخية.
هذا يتيح اختبار المسار كاملًا (التقاط → تحليل → اتجاه → تنبؤ → تنبيه) دون كاميرات حقيقية.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import cv2
import numpy as np

# المحاكي مُعايَر على مناخ خليجي نموذجي (متوسطات شهرية: العظمى، الصغرى °م)
_CLIMATE = {1: (24.0, 14.5), 2: (25.5, 15.5), 3: (28.5, 18.0), 4: (33.0, 21.5), 5: (37.5, 25.5),
            6: (39.5, 28.0), 7: (41.0, 30.5), 8: (41.0, 30.5), 9: (38.5, 27.5), 10: (35.0, 23.5),
            11: (30.0, 19.0), 12: (26.0, 16.0)}

W, H = 960, 540          # حجم اللقطة
TW, TH = 600, 900        # حجم سطح الطريق قبل الإسقاط المنظوري
HORIZON = 0.40           # موضع الأفق نسبةً للارتفاع
ROAD_POLY = [(0.02, 1.0), (0.98, 1.0), (0.60, HORIZON + 0.02), (0.40, HORIZON + 0.02)]


def road_roi() -> list[list[float]]:
    """منطقة الطريق في الصورة (نِسَب) — تستخدمها خوارزمية التحليل."""
    return [[0.08, 0.97], [0.92, 0.97], [0.585, 0.50], [0.415, 0.50]]


def _parse(d: str) -> date:
    return date.fromisoformat(d[:10])


def stress(surface: date, at: date, heavy_pct: float, aadt: float) -> float:
    """إجهاد تراكمي (وحدات أسبوعية): حراري × مروري، منذ تاريخ الرصف."""
    traffic = (aadt / 60000) ** 0.6 * (1 + heavy_pct / 25)
    s, d = 0.0, surface
    while d < at:
        tmax, tmin = _CLIMATE[d.month]
        heat = max(0.15, (tmax - 27) / 10) * (1 + max(0, (tmax - tmin) - 9) / 10)
        s += heat * traffic
        d += timedelta(days=7)
    return s


class Scene:
    """عناصر الرصف الثابتة لكل كاميرا: مسارات التشققات المحتملة ومواضع الحفر."""

    def __init__(self, seed: int):
        rng = np.random.default_rng(seed)
        self.seed = seed
        self.base = self._asphalt(rng)
        self.cracks = []
        for i in range(26):
            kind = rng.choice(["long", "trans", "alligator"], p=[0.45, 0.35, 0.20])
            x, y = rng.uniform(70, TW - 70), rng.uniform(120, TH - 60)
            ang = {"long": math.pi / 2, "trans": 0.0}.get(kind, rng.uniform(0, math.pi))
            ang += rng.normal(0, 0.25)
            pts = [(x, y)]
            n = int(rng.integers(25, 60))
            for _ in range(n):
                ang += rng.normal(0, 0.35 if kind == "alligator" else 0.18)
                step = rng.uniform(5, 9)
                x = float(np.clip(x + math.cos(ang) * step, 10, TW - 10))
                y = float(np.clip(y + math.sin(ang) * step, 10, TH - 10))
                pts.append((x, y))
            # عتبة ظهور التشقق (بوحدات الإجهاد × معدّل التدهور)
            self.cracks.append({"pts": pts, "onset": float(rng.uniform(15, 140)) + i * 4,
                                "width": int(rng.integers(1, 4)), "kind": kind})
        self.potholes = [{"x": rng.uniform(110, TW - 110), "y": rng.uniform(300, TH - 80),
                          "onset": float(rng.uniform(120, 260)), "r": rng.uniform(16, 30),
                          "ax": rng.uniform(0.7, 1.3)} for _ in range(5)]

    @staticmethod
    def _asphalt(rng) -> np.ndarray:
        noise = rng.normal(0, 1, (TH // 4, TW // 4)).astype(np.float32)
        noise = cv2.resize(cv2.GaussianBlur(noise, (0, 0), 1.2), (TW, TH))
        fine = rng.normal(0, 6, (TH, TW)).astype(np.float32)
        g = 92 + noise * 7 + fine
        img = np.dstack([g * 0.98, g, g * 1.03])
        img = np.clip(img, 0, 255).astype(np.uint8)
        # علامات المسارات: خطّا الحافة وخطّان متقطعان
        for x in (40, TW - 40):
            cv2.line(img, (x, 0), (x, TH), (200, 215, 220), 7)
        for x in (TW // 3 + 15, 2 * TW // 3 - 15):
            for y in range(0, TH, 90):
                cv2.line(img, (x, y), (x, y + 45), (225, 230, 230), 6)
        return img


_scenes: dict[int, Scene] = {}


def _scene(seed: int) -> Scene:
    if seed not in _scenes:
        _scenes[seed] = Scene(seed)
    return _scenes[seed]


def _sudden_at(event: dict | None) -> datetime | None:
    if not event or not event.get("at"):
        return None
    return datetime.fromisoformat(event["at"]).astimezone(timezone.utc)


def render_surface(source: dict, meta: dict, at: datetime) -> np.ndarray:
    sc = _scene(int(source.get("seed", 1)))
    img = sc.base.copy()
    rate = float(source.get("deterioration_rate", 1.0))
    surface = _parse(meta.get("surface_date", "2020-01-01"))
    last_maint = meta.get("last_maintenance")
    if last_maint and _parse(last_maint) > surface:
        surface = _parse(last_maint)  # إعادة الرصف تعيد الحالة إلى البداية
    rep_at = _sudden_at(source.get("repair_event"))
    if rep_at and at >= rep_at:
        surface = rep_at.date()  # إصلاح محاكى: كشط وإعادة رصف في تاريخ الحدث
    s = stress(surface, at.date(), float(meta.get("heavy_vehicle_pct", 10)), float(meta.get("aadt", 50000))) * rate / 8

    for c in sc.cracks:
        if s <= c["onset"]:
            continue
        frac = min(1.0, (s - c["onset"]) / 90)
        pts = c["pts"][: max(2, int(len(c["pts"]) * frac))]
        arr = np.array(pts, np.int32).reshape(-1, 1, 2)
        width = c["width"]
        cv2.polylines(img, [arr], False, (28, 30, 32), width, cv2.LINE_AA)
        if c["kind"] == "alligator" and frac > 0.5:  # تفرعات شبكية
            rng = np.random.default_rng(sc.seed + int(c["onset"]))
            for p in pts[::6]:
                a = rng.uniform(0, 2 * math.pi)
                q = (int(p[0] + 18 * math.cos(a)), int(p[1] + 18 * math.sin(a)))
                cv2.line(img, (int(p[0]), int(p[1])), q, (34, 36, 38), 2, cv2.LINE_AA)
    for p in sc.potholes:
        if s <= p["onset"]:
            continue
        r = p["r"] * min(1.6, 0.5 + (s - p["onset"]) / 80)
        _pothole(img, p["x"], p["y"], r, p["ax"])

    ev = source.get("sudden_event")
    ev_at = _sudden_at(ev)
    clear_at = datetime.fromisoformat(ev["clear_at"]) if ev and ev.get("clear_at") else None
    repaired = rep_at is not None and ev_at is not None and rep_at > ev_at and at >= rep_at
    if ev_at and at >= ev_at and not (clear_at and at >= clear_at) and not repaired:
        rng = np.random.default_rng(sc.seed + 99)
        x, y = TW * rng.uniform(0.35, 0.65), TH * rng.uniform(0.62, 0.8)
        if ev.get("kind") == "debris":
            for _ in range(9):
                cx, cy = x + rng.normal(0, 35), y + rng.normal(0, 20)
                cv2.ellipse(img, (int(cx), int(cy)), (int(rng.uniform(10, 22)), int(rng.uniform(6, 12))),
                            float(rng.uniform(0, 180)), 0, 360, (40, 52, 66), -1, cv2.LINE_AA)
        else:
            _pothole(img, x, y, 46, 1.25)
    return img


def _pothole(img, x, y, r, ax):
    center, axes = (int(x), int(y)), (int(r * ax), int(r))
    cv2.ellipse(img, center, (axes[0] + 5, axes[1] + 5), 0, 0, 360, (58, 60, 62), -1, cv2.LINE_AA)
    cv2.ellipse(img, center, axes, 0, 0, 360, (22, 23, 25), -1, cv2.LINE_AA)
    cv2.ellipse(img, (center[0] - 3, center[1] - 3), (axes[0] // 2, axes[1] // 2), 0, 0, 360,
                (12, 13, 15), -1, cv2.LINE_AA)


def _project(surface: np.ndarray) -> np.ndarray:
    src = np.float32([[0, TH], [TW, TH], [TW, 0], [0, 0]])
    dst = np.float32([[ROAD_POLY[i][0] * W, ROAD_POLY[i][1] * H] for i in range(4)])
    M = cv2.getPerspectiveTransform(src, dst)
    frame = np.zeros((H, W, 3), np.uint8)
    # سماء وأرض رملية وجزيرة وسطية
    frame[: int(H * HORIZON)] = (230, 205, 170)
    frame[int(H * HORIZON):] = (120, 170, 205)
    road = cv2.warpPerspective(surface, M, (W, H), flags=cv2.INTER_LINEAR)
    mask = cv2.warpPerspective(np.full((TH, TW), 255, np.uint8), M, (W, H))
    frame[mask > 0] = road[mask > 0]
    return frame


def _vehicles(frame: np.ndarray, rng) -> None:
    for _ in range(int(rng.integers(1, 5))):
        t = rng.uniform(0.15, 1.0)  # العمق (0 أفق، 1 أسفل)
        y = int(H * (HORIZON + 0.02 + t * (1 - HORIZON - 0.06)))
        half = (0.10 + 0.48 * t) * W
        x = int(W / 2 + rng.uniform(-0.75, 0.75) * half)
        w, h = int(70 * (0.25 + t)), int(46 * (0.25 + t))
        color = tuple(int(c) for c in rng.choice([[240, 240, 240], [30, 30, 30], [40, 40, 160], [150, 120, 60], [190, 190, 190]]))
        cv2.rectangle(frame, (x - w // 2, y - h), (x + w // 2, y), color, -1)
        cv2.rectangle(frame, (x - w // 3, y - h - h // 3), (x + w // 3, y - h), color, -1)
        cv2.ellipse(frame, (x, y + 3), (w // 2, 5), 0, 0, 360, (20, 20, 20), -1)


def capture_frames(source: dict, meta: dict, at: datetime, n: int) -> list[np.ndarray]:
    """يحاكي «دفعة» إطارات من الكاميرا: الطريق نفسه مع مركبات مختلفة في كل إطار."""
    surface = render_surface(source, meta, at)
    base = _project(surface)
    rng = np.random.default_rng(int(at.timestamp()) // 60 + int(source.get("seed", 1)))
    gain = rng.uniform(0.85, 1.15)  # إضاءة تختلف بين يوم وآخر
    frames = []
    for _ in range(n):
        f = base.copy()
        _vehicles(f, rng)
        f = np.clip(f.astype(np.float32) * gain + rng.normal(0, 3, f.shape), 0, 255).astype(np.uint8)
        frames.append(f)
    return frames
