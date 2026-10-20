"""نموذج تقدير مخاطر تدهور الرصف — قابل للتفسير.

نموذج لوجستي بأوزان معلنة يجمع ثمانية عوامل مطبَّعة (0–1):
  حالة الرصف الحالية، سرعة التدهور (ميل مؤشر الحالة عبر الأسابيع)، الحفر، الإجهاد الحراري،
  المدى الحراري اليومي، الحمل المروري والشاحنات، عمر الطبقة منذ آخر صيانة، والحوادث القريبة.
يُخرج احتمال الوصول لحالة تستوجب الصيانة خلال 90 يومًا، ومساهمة كل عامل في النتيجة،
وإسقاطًا لمؤشر الحالة لـ12 أسبوعًا، وتوصيات عملية.

الأوزان الحالية مبدئية مبنية على أدبيات هندسة الرصف؛ بعد تجميع سجلات صيانة فعلية يمكن
معايرتها بالانحدار اللوجستي (fit_weights) وتبقى المخرجات قابلة للتفسير بالطريقة نفسها.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np

from . import config

WEIGHTS = {
    "condition": 3.4, "trend": 2.4, "potholes": 1.6, "heat": 0.5,
    "thermal_range": 0.5, "traffic": 1.0, "age": 0.8, "incidents": 0.4,
    "rutting": 1.0, "sand": 0.3, "events": 0.5,
}
INTERCEPT = -4.3

FACTOR_AR = {
    "condition": "حالة الرصف الحالية",
    "trend": "سرعة التدهور عبر الأسابيع",
    "potholes": "وجود حفر",
    "heat": "الإجهاد الحراري (درجات الحرارة العالية)",
    "thermal_range": "الفرق بين حرارة النهار والليل",
    "traffic": "الحمل المروري والشاحنات الثقيلة",
    "age": "عمر الطبقة منذ آخر رصف/صيانة",
    "incidents": "الحوادث المرورية القريبة",
    "rutting": "خطر التخدد (حرارة الرصف × الشاحنات × درجة الرابط)",
    "sand": "رمال على سطح الطريق",
    "events": "سيول أو عاصفة في الأيام الأخيرة",
}

LEVELS = [(25, "low", "منخفض"), (50, "medium", "متوسط"), (75, "high", "مرتفع"), (101, "critical", "حرج")]


def _clip(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def weekly(history: list[dict]) -> list[dict]:
    """نقطة واحدة لكل أسبوع: وسيط مؤشر الحالة لكل لقطات الأسبوع (اليومية والأسبوعية).
    وسيط 5–7 أيام أثبت من لقطة واحدة: يوم مبتل أو ظل أو مركبة متوقفة لا يغيّر النتيجة.
    الأسبوع الجاري يدخل بما التُقط فيه حتى الآن، فإذا تكرر عيب في أغلب أيامه ظهر أثره فورًا."""
    groups: dict[tuple, list[dict]] = {}
    for h in sorted(history, key=lambda h: h["ts"]):
        if h.get("condition_index") is None:
            continue
        y, w, _ = _ts(h["ts"]).isocalendar()
        groups.setdefault((y, w), []).append(h)
    return [{**g[-1], "condition_index": float(np.median([x["condition_index"] for x in g])), "samples": len(g)}
            for _, g in sorted(groups.items())]


def smooth(history: list[dict], window: int = 3) -> list[dict]:
    """سلسلة الاتجاه: الأسابيع المكتملة نقطة واحدة لكل أسبوع (وسيط أيامه)، والأيام السبعة الأخيرة نقاط يومية،
    ثم وسيط متحرك لثلاث نقاط. أسبوع أو يوم شاذ منفرد يُخمد، والتغيّر الذي يتكرر يومين متتاليين (حفرة مفاجئة
    بقيت) يظهر فورًا بدل انتظار نهاية الأسبوع."""
    pts = sorted((h for h in history if h.get("condition_index") is not None), key=lambda h: h["ts"])
    if not pts:
        return []
    week_ago = (_ts(pts[-1]["ts"]) - timedelta(days=7)).isoformat()
    trend = weekly([h for h in pts if h["ts"] < week_ago]) + [h for h in pts if h["ts"] >= week_ago]
    # إعادة رصف/إصلاح = قفزة كبيرة للأعلى: تبدأ السلسلة من بعدها، فلا تؤثر الحالة القديمة على التنبؤ
    for i in range(len(trend) - 1, 0, -1):
        if trend[i]["condition_index"] - trend[i - 1]["condition_index"] >= 15:
            trend = trend[i:]
            break
    out = []
    for i, h in enumerate(trend):
        vals = [x["condition_index"] for x in trend[max(0, i - window + 1): i + 1]]
        out.append({**h, "condition_index": float(np.median(vals))})
    return out


def ci_slope(history: list[dict], weeks: int = 12) -> float:
    """ميل مؤشر الحالة (نقطة/أسبوع) بانحدار خطي موزون يعطي الأحدث وزنًا أكبر."""
    if len(history) < 2:
        return 0.0
    t_end = _ts(history[-1]["ts"])
    pts = [(-(t_end - _ts(h["ts"])).total_seconds() / 604800, h["condition_index"]) for h in history
           if h.get("condition_index") is not None and (t_end - _ts(h["ts"])).days <= weeks * 7]
    if len(pts) < 2:
        return 0.0
    x = np.array([p[0] for p in pts])
    y = np.array([p[1] for p in pts])
    if np.ptp(x) < 0.5:
        return 0.0
    w = np.exp(x / weeks)  # x سالب للأقدم
    A = np.vstack([x, np.ones_like(x)]).T * np.sqrt(w)[:, None]
    slope, _ = np.linalg.lstsq(A, y * np.sqrt(w), rcond=None)[0]
    return float(slope)


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _years_since(d: str | None, at: date) -> float:
    if not d:
        return 5.0
    return max(0.0, (at - date.fromisoformat(d[:10])).days / 365.25)


def assess(camera: dict, history: list[dict], heat: dict, outlook: dict, incidents: int = 0,
           at: datetime | None = None, gulf: dict | None = None) -> dict:
    at = at or datetime.now().astimezone()
    meta = camera.get("meta", {})
    latest = history[-1]
    series = smooth(history)
    ci = float(series[-1]["condition_index"])
    metrics = latest.get("metrics") or {}
    slope = ci_slope(series)
    age_from = meta.get("last_maintenance") or meta.get("surface_date")
    traffic_n = _clip(meta.get("aadt", 40000) / 100000) * 0.5 + _clip(meta.get("heavy_vehicle_pct", 10) / 35) * 0.5

    feats = {
        "condition": _clip((100 - ci) / 100),
        "trend": _clip(-slope / 1.5),
        "potholes": _clip(latest.get("pothole_count", 0) / 3),
        "heat": _clip((heat["mean_tmax"] - 30) / 15) * 0.7 + _clip(heat["days_above_45"] / 10) * 0.3,
        "thermal_range": _clip((heat["mean_diurnal_range"] - 8) / 8),
        "traffic": traffic_n,
        "age": _clip(_years_since(age_from, at.date()) / 12),
        "incidents": _clip(incidents / 5),
        "rutting": float((gulf or {}).get("rutting_risk", 0.0)),
        "sand": _clip(metrics.get("sand_cover", 0.0) / 0.25),
        "events": 1.0 if (gulf or {}).get("events") else 0.0,
    }
    z = INTERCEPT + sum(WEIGHTS[k] * v for k, v in feats.items())
    prob = 1 / (1 + math.exp(-z))
    score = round(100 * prob, 1)
    level, level_ar = next((lv, ar) for lim, lv, ar in LEVELS if score < lim)

    contrib = {k: WEIGHTS[k] * v for k, v in feats.items()}
    total = sum(contrib.values()) or 1.0
    factors = sorted(({
        "key": k, "label": FACTOR_AR[k], "value": round(feats[k], 3),
        "weight": WEIGHTS[k], "share": round(100 * contrib[k] / total, 1),
    } for k in feats), key=lambda f: -f["share"])

    # إسقاط مؤشر الحالة: الميل المرصود مع حد أدنى للتدهور الطبيعي، مضروبًا بعامل حرارة الفترة القادمة
    base_decline = -0.08 * (feats["heat"] + traffic_n + feats["age"])
    eff = min(slope, 0.0) if slope < -0.05 else base_decline
    season = min(1.5, max(0.6, 1 + (outlook["mean_tmax"] - 35) / 20))
    eff *= season
    forecast = [{"week": w, "ts": (at + timedelta(weeks=w)).isoformat(),
                 "condition_index": round(max(0.0, ci + eff * w), 1)} for w in range(1, 13)]
    thr = config.MAINTENANCE_THRESHOLD
    if ci <= thr:
        weeks_to = 0.0
    elif eff < 0:
        weeks_to = round((ci - thr) / -eff, 1)
    else:
        weeks_to = None

    return {
        "score": score, "level": level, "level_ar": level_ar, "prob_90d": round(prob, 3),
        "weeks_to_threshold": weeks_to, "ci": ci, "ci_slope": round(slope, 3),
        "effective_slope": round(eff, 3), "season_factor": round(season, 2),
        "factors": factors, "features": feats, "heat": heat, "outlook": outlook,
        "forecast": forecast,
        "priority": round(score * (0.7 + 0.3 * traffic_n), 1),
        "recommendations": recommend(ci, latest, metrics, feats, slope, weeks_to, level, gulf or {}),
        "gulf": gulf,
        "next_inspection_days": {"critical": 1, "high": 3, "medium": 7, "low": 14}[level],
    }


def recommend(ci, latest, metrics, feats, slope, weeks_to, level, gulf=None) -> list[dict]:
    gulf = gulf or {}
    recs = []
    thr = config.MAINTENANCE_THRESHOLD
    if ci <= thr:
        recs.append({"priority": "عاجل", "text": f"مؤشر الحالة ({ci:.0f}) دون عتبة الصيانة ({thr:.0f}) — جدولة فحص ميداني وصيانة تصحيحية فورًا."})
    if latest.get("pothole_count", 0) > 0:
        recs.append({"priority": "عاجل", "text": "ردم الحفر المكتشفة خلال 48 ساعة ووضع إشارات تحذير مؤقتة لسلامة السائقين."})
    if metrics.get("alligator_density", 0) > 0.8:
        recs.append({"priority": "مرتفع", "text": "تشقق تمساحي يدل على ضعف الطبقات السفلية — فحص إنشائي ثم كشط وإعادة رصف للمقطع بدل الترقيع."})
    if 0.2 < metrics.get("crack_density", 0) and ci > thr:
        recs.append({"priority": "مرتفع" if slope < -0.5 else "متوسط",
                     "text": "سدّ التشققات (Crack Sealing) قبل ذروة الصيف لمنع تسرب المياه والرمال وتوسّعها."})
    if weeks_to is not None and 0 < weeks_to <= 12:
        recs.append({"priority": "مرتفع", "text": f"يُتوقع بلوغ عتبة الصيانة خلال ~{weeks_to:.0f} أسبوع — إدراج المقطع في خطة الصيانة الوقائية القادمة."})
    if feats["heat"] > 0.5 and feats["traffic"] > 0.5:
        recs.append({"priority": "متوسط", "text": "عند إعادة الرصف: خلطة إسفلتية معدّلة بالبوليمر (PMB) مقاومة للتخدد في الحرارة العالية والأحمال الثقيلة."})
    for ev in gulf.get("events", []):
        recs.append({"priority": "مرتفع", "text": f"فحص بعد الحدث ({ev['date']}): {ev['text']}"})
    if gulf.get("rutting_risk", 0) >= 0.6:
        recs.append({"priority": "مرتفع", "text": f"خطر تخدد مرتفع: الرصف بلغ ~{gulf['pavement_t7max']:.0f}°م مع ~{gulf['trucks_per_day']:,} شاحنة/يوم — "
                     "قياس عمق التخدد بمسطرة 3 م في مسارات العجلات، وتوجيه الشاحنات للمسار الأيمن بعيدًا عن ساعات الذروة الحرارية (12–4 م)."})
    if gulf.get("pg_deficit_grades", 0) > 0:
        recs.append({"priority": "مرتفع" if gulf["pg_deficit_grades"] > 1 else "متوسط",
                     "text": f"الرابط الحالي PG {gulf['binder_pg']} أقل من المطلوب لمناخ المنطقة PG {gulf['pg_design']} "
                             f"(حرارة الرصف التصميمية ~{gulf['pg_design_t7']:.0f}°م) — عند إعادة الرصف: رابط PG {gulf['pg_design']} أو معدّل بالبوليمر."})
    if metrics.get("sand_cover", 0) >= 0.10:
        recs.append({"priority": "متوسط", "text": f"رمال تغطي ~{metrics['sand_cover'] * 100:.0f}% من سطح الطريق — إزالة فورية (تقلل الاحتكاك وتسرّع البري)، "
                     "ودراسة سياج رملي أو تشجير مصدّ في الجهة المواجهة للرياح."})
    if slope < -0.8:
        recs.append({"priority": "متوسط", "text": "التدهور متسارع — تقليص فترة التحليل لهذه الكاميرا إلى يومية حتى المعالجة."})
    if not recs:
        recs.append({"priority": "منخفض", "text": "الحالة جيدة — الاستمرار في المراقبة الأسبوعية الآلية."})
    return recs


def fit_weights(X: np.ndarray, y: np.ndarray, iters: int = 3000, lr: float = 0.1, l2: float = 0.01):
    """معايرة الأوزان من سجلات صيانة فعلية (X: عوامل مطبّعة بترتيب WEIGHTS، y: 1 إن احتاج صيانة خلال 90 يومًا)."""
    w = np.array(list(WEIGHTS.values()), float)
    b = INTERCEPT
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = p - y
        w -= lr * (X.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return dict(zip(WEIGHTS, w.round(3))), round(float(b), 3)
