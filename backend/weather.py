"""بيانات الحرارة لكل منطقة — Open-Meteo (أرشيف + توقعات، مجاني بلا مفتاح) مع المناخ الشهري احتياطيًا.

الحرارة العالية تليّن الإسفلت وتسرّع التخدد، والفرق الكبير بين نهار وليل يسبب إجهادًا حراريًا
وتشققات؛ لذا يحسب النموذج مؤشرَين: متوسط العظمى وأيام ما فوق 45°م، ومتوسط المدى اليومي.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta

import httpx

from . import config, db

log = logging.getLogger("darb.weather")
_fetch_lock = threading.Lock()
_backoff_until: dict[str, float] = {}  # بعد فشل الطلب لا نعيد المحاولة قبل 15 دقيقة (احترام حدود الخدمة المجانية)


def climate(d: date, region: str) -> tuple[float, float]:
    """المتوسط المناخي للشهر في المنطقة — يُستخدم عند تعذّر Open-Meteo."""
    return config.REGIONS[region]["climate"][d.month]


DAILY = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum", "wind_gusts_10m_max", "shortwave_radiation_sum")


def _fetch(start: date, end: date, region: str) -> dict[str, tuple]:
    r_cfg = config.REGIONS[region]
    today = date.today()
    out: dict[str, tuple] = {}
    params = {
        "latitude": r_cfg["lat"], "longitude": r_cfg["lng"],
        "daily": ",".join(DAILY), "timezone": r_cfg["tz"],
    }
    calls = []
    # الأرشيف متأخر بضعة أيام؛ ما بعده يؤخذ من واجهة التوقعات (past_days)
    archive_end = min(end, today - timedelta(days=6))
    if start <= archive_end:
        calls.append(("https://archive-api.open-meteo.com/v1/archive",
                      {**params, "start_date": start.isoformat(), "end_date": archive_end.isoformat()}))
    if end > archive_end:
        calls.append(("https://api.open-meteo.com/v1/forecast", {**params, "past_days": 10, "forecast_days": 16}))
    with httpx.Client(timeout=15, headers={"User-Agent": config.USER_AGENT}) as client:
        for url, p in calls:
            r = client.get(url, params=p)
            r.raise_for_status()
            daily = r.json()["daily"]
            cols = [daily.get(k) or [None] * len(daily["time"]) for k in DAILY]
            for d, hi, lo, pr, gu, ra in zip(daily["time"], *cols):
                if hi is not None and lo is not None:
                    out[d] = (float(hi), float(lo), pr, gu, ra)
    return out


def daily_range(start: date, end: date, region: str) -> list[dict]:
    """قائمة أيام [start, end] بالعظمى والصغرى، من الذاكرة المؤقتة ثم Open-Meteo ثم المناخ."""
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    cached = {r["date"]: r for r in db.query(
        "SELECT * FROM weather WHERE region=? AND date BETWEEN ? AND ?", (region, start.isoformat(), end.isoformat()))}
    horizon = date.today() + timedelta(days=15)  # لا توقعات بعد ذلك — يُستخدم المناخ
    missing = [d for d in days if d.isoformat() not in cached and d <= horizon]
    if missing and config.WEATHER_ENABLED and time.time() >= _backoff_until.get(region, 0):
        try:
            with _fetch_lock:
                fetched = _fetch(min(missing), max(missing), region)
            with db.tx() as c:
                for d, (hi, lo, pr, gu, ra) in fetched.items():
                    c.execute("INSERT OR REPLACE INTO weather(region,date,tmax,tmin,source,precip,gust,radiation) VALUES (?,?,?,?,?,?,?,?)",
                              (region, d, hi, lo, "open-meteo", pr, gu, ra))
                    cached[d] = {"date": d, "tmax": hi, "tmin": lo, "source": "open-meteo", "precip": pr, "gust": gu, "radiation": ra}
        except Exception as e:  # الشبكة غير متاحة — نكمل بالمناخ
            _backoff_until[region] = time.time() + 900
            log.warning("Open-Meteo unavailable for %s (%s); using climatology for 15 min", region, str(e)[:120])
    out = []
    for d in days:
        r = cached.get(d.isoformat())
        if r is None:
            hi, lo = climate(d, region)
            r = {"date": d.isoformat(), "tmax": hi, "tmin": lo, "source": "climatology"}
        out.append(r)
    return out


def heat_features(end: date, region: str, days: int = 30) -> dict:
    rows = daily_range(end - timedelta(days=days - 1), end, region)
    tmax = [r["tmax"] for r in rows]
    rng = [r["tmax"] - r["tmin"] for r in rows]
    return {
        "mean_tmax": round(sum(tmax) / len(tmax), 1),
        "days_above_45": sum(1 for t in tmax if t >= 45),
        "mean_diurnal_range": round(sum(rng) / len(rng), 1),
        "source": "open-meteo" if any(r["source"] == "open-meteo" for r in rows) else "climatology",
    }


def outlook(start: date, region: str, days: int = 14) -> dict:
    """توقعات الأسبوعين القادمين (أو المناخ) لتعديل سرعة التدهور المتوقعة."""
    rows = daily_range(start, start + timedelta(days=days - 1), region)
    tmax = [r["tmax"] for r in rows]
    return {"mean_tmax": round(sum(tmax) / len(tmax), 1), "max_tmax": max(tmax)}
