"""فيزياء طرق الخليج: ما لا تراه نماذج العيوب العالمية المدرّبة على طرق اليابان والهند وأوروبا.

1. حرارة الرصف: نموذج SHRP/Superpave لحرارة الإسفلت على عمق 20 مم من حرارة الهواء وخط العرض،
   مصحّحًا بالإشعاع الشمسي الفعلي (Open-Meteo) نسبةً إلى إشعاع السماء الصافية (FAO-56).
2. درجة الرابط المطلوبة (PG): متوسط أعلى 7 أيام لحرارة الرصف يحدد الدرجة العليا اللازمة
   (58/64/70/76/82)، وتُقارن بالرابط المفترض للطريق. نقص الدرجة = تليّن مبكر وتخدد.
3. خطر التخدد: تعرّض حراري (درجات-أيام فوق 50°م في الرصف) × أحمال الشاحنات × نقص درجة الرابط.
4. الرمال على الطريق: تجزئة لونية داخل منطقة الطريق (البيج الرملي يختلف عن رمادي الإسفلت وأصفر العلامات).
5. الأحداث المتطرفة: سيول (أمطار غزيرة في بيئة جافة) وعواصف رملية/رياح شديدة تستوجب فحصًا بعد الحدث.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import cv2
import numpy as np

from . import config, vision, weather

PG_GRADES = (52, 58, 64, 70, 76, 82)
RUT_BASE_C = 50.0  # فوق هذه الحرارة في الرصف يبدأ التليّن الذي يراكم التخدد تحت الأحمال


def pavement_max(t_air: float, lat: float, radiation: float | None = None, day: date | None = None) -> float:
    """أعلى حرارة للإسفلت على عمق 20 مم (°م) — نموذج SHRP (Solaimanian & Kennedy):
    T20 = (Tair − 0.00618·Lat² + 0.2289·Lat + 42.2)·0.9545 − 17.78
    والفرق عن حرارة الهواء يُقاس بنسبة الإشعاع الفعلي إلى إشعاع السماء الصافية (الغيوم والغبار تخفّضه)."""
    lat = abs(lat)
    t20 = (t_air - 0.00618 * lat * lat + 0.2289 * lat + 42.2) * 0.9545 - 17.78
    if radiation is not None and day is not None:
        clear = clear_sky_radiation(lat, day)
        if clear > 0:
            t20 = t_air + (t20 - t_air) * min(1.1, max(0.3, radiation / clear))
    return round(t20, 1)


def clear_sky_radiation(lat: float, day: date) -> float:
    """إشعاع السماء الصافية اليومي (MJ/m²) = 0.75 × الإشعاع خارج الغلاف الجوي (FAO-56، المعادلتان 21 و37)."""
    j = day.timetuple().tm_yday
    phi = math.radians(lat)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    dec = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(dec))))
    ra = 24 * 60 / math.pi * 0.0820 * dr * (ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))
    return 0.75 * ra


def pg_required(t7max: float) -> int:
    """أدنى درجة عليا للرابط (PG) تتحمل متوسط أعلى 7 أيام لحرارة الرصف."""
    return next((g for g in PG_GRADES if g >= t7max), PG_GRADES[-1])


def binder_pg(camera: dict) -> int:
    region = camera.get("region") or config.REGION_KEYS[0]
    return int(camera.get("meta", {}).get("binder_pg") or config.REGIONS.get(region, {}).get("binder_pg", 70))


def design_pg(camera: dict) -> dict:
    """الدرجة اللازمة للتصميم (Superpave): أحر أسبوع بموثوقية 98% ≈ متوسط عظمى أحر شهر + 7°م
    (أحر أسبوع فوق المتوسط الشهري ~3°م + انحرافان معياريان ~4°م)، ثم درجة إضافية للأحمال الثقيلة
    (أكثر من 10 آلاف شاحنة يوميًا ≈ أكثر من 30 مليون محور مكافئ خلال العمر التصميمي)."""
    region = camera.get("region") or config.REGION_KEYS[0]
    r = config.REGIONS[region]
    month, (hi, _) = max(r["climate"].items(), key=lambda kv: kv[1][0])
    t7 = pavement_max(hi + 7.0, r["lat"])
    meta = camera.get("meta", {})
    heavy = meta.get("aadt", 0) * meta.get("heavy_vehicle_pct", 0) / 100 > 10000
    pg = pg_required(t7)
    if heavy:
        pg = PG_GRADES[min(len(PG_GRADES) - 1, PG_GRADES.index(pg) + 1)]
    return {"t7max": t7, "pg": pg, "month": month, "traffic_bump": heavy}


def pavement_features(camera: dict, end: date, days: int = 30) -> dict:
    """مؤشرات الفيزياء الخليجية لكاميرا في آخر 30 يومًا + الأيام القادمة."""
    region = camera.get("region") or config.REGION_KEYS[0]
    lat = config.REGIONS[region]["lat"]
    rows = weather.daily_range(end - timedelta(days=days - 1), end + timedelta(days=7), region)
    past = [r for r in rows if r["date"] <= end.isoformat()]
    ahead = [r for r in rows if r["date"] > end.isoformat()]

    def tpav(r):
        return pavement_max(r["tmax"], lat, r.get("radiation"), date.fromisoformat(r["date"]))

    pav = [tpav(r) for r in past]
    pav_ahead = [tpav(r) for r in ahead] or [pav[-1]]
    t7 = float(np.mean(sorted(pav)[-7:]))
    dd = sum(max(0.0, t - RUT_BASE_C) for t in pav)  # درجات-أيام التليّن في 30 يومًا
    actual = binder_pg(camera)
    need_now, design = pg_required(t7), design_pg(camera)
    deficit = max(0, PG_GRADES.index(design["pg"]) - PG_GRADES.index(actual)) if actual in PG_GRADES else 0

    meta = camera.get("meta", {})
    trucks = meta.get("aadt", 40000) * meta.get("heavy_vehicle_pct", 10) / 100
    load = min(1.0, trucks / 15000)  # ~15 ألف شاحنة/يوم = أحمال ثقيلة جدًا
    heat = min(1.0, dd / 300)        # 300 درجة-يوم/شهر ≈ صيف الخليج القاسي (رصف ~60°م يوميًا)
    rut = min(1.0, heat * (0.35 + 0.65 * load) * (1 + 0.5 * deficit) + (0.15 if need_now > actual else 0.0))

    events = extreme_events(region, end)
    return {
        "pavement_t7max": round(t7, 1), "pavement_today": pav[-1], "pavement_ahead_max": round(max(pav_ahead), 1),
        "rut_degree_days": round(dd, 1), "binder_pg": actual, "pg_needed_now": need_now,
        "pg_design": design["pg"], "pg_design_t7": design["t7max"], "pg_deficit_grades": deficit,
        "trucks_per_day": round(trucks), "rutting_risk": round(rut, 3),
        "rutting_level": "high" if rut >= 0.6 else "medium" if rut >= 0.3 else "low",
        "events": events,
        "source": "open-meteo" if any(r.get("source") == "open-meteo" for r in past) else "climatology",
    }


def extreme_events(region: str, end: date, days: int = 3) -> list[dict]:
    """أحداث الأيام الثلاثة الأخيرة التي تستوجب فحصًا بعد الحدث."""
    arid = config.REGIONS[region].get("climate_kind") in ("desert", "semiarid")
    rain_thr = 20.0 if arid else 50.0  # 20 مم في يوم واحد سيلٌ في بيئة جافة
    out = []
    for r in weather.daily_range(end - timedelta(days=days - 1), end, region):
        if (r.get("precip") or 0) >= rain_thr:
            out.append({"date": r["date"], "kind": "flood", "value": r["precip"],
                        "text": f"أمطار غزيرة {r['precip']:.0f} مم — خطر سيول: فحص الأكتاف والعبّارات وهبوط الطريق."})
        if (r.get("gust") or 0) >= 60:
            out.append({"date": r["date"], "kind": "wind", "value": r["gust"],
                        "text": f"رياح شديدة {r['gust']:.0f} كم/س — احتمال زحف رمال أو مخلّفات على الطريق."})
    return out


def sand_cover(img: np.ndarray, roi: list[list[float]]) -> float:
    """نسبة سطح الطريق المغطّى بلون رملي: بيج (تدرّج 8–24 في OpenCV) بتشبّع متوسط وسطوع عالٍ.
    الإسفلت رمادي (تشبّع منخفض)، والعلامات الصفراء مشبعة جدًا، فيُستبعد كلاهما.
    والرمل بقع تختلف عن لون الطريق نفسه: إذا كان السطح كله مائلًا للبيج (خرسانة فاتحة في ضوء الصباح الدافئ)
    فلا يُحتسب إلا ما يزيد تشبّعه بوضوح على لون الرصف النظيف (SR-55: «رمال 44%» كانت شمس الصباح على خرسانة نظيفة)."""
    mask = vision.roi_mask(img.shape, roi) > 0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1].astype(np.int16), hsv[..., 2]
    n = int(mask.sum())
    if not n:
        return 0.0
    road_s = float(np.percentile(s[mask], 30))  # لون الرصف النظيف (الثلث الأقل تشبعًا) — يبقى صحيحًا ما دام الرمل دون 70%
    sand = (h >= 8) & (h <= 24) & (s >= max(45, road_s + 18)) & (s <= 150) & (v >= 120)
    return round(float((sand & mask).sum()) / n, 4)
