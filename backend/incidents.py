"""حوادث المرور اللحظية من Dubai Pulse (بيانات شرطة دبي المفتوحة) — اختياري.

يتطلب مفتاحًا وسرًّا مجانيين من بوابة dubaipulse.gov.ae. تُستخدم الحوادث عاملًا في نموذج
المخاطر (الحوادث المتكررة قرب مقطع متدهور مؤشر خطر على السلامة)، وتولّد تنبيهًا فوريًا عند
حادث قريب جدًا من كاميرا لفحص اللقطة التالية.
"""
from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config

log = logging.getLogger("darb.incidents")

TOKEN_URL = os.getenv("DUBAI_PULSE_TOKEN_URL",
                      "https://api.dubaipulse.gov.ae/oauth/client_credential/accesstoken?grant_type=client_credentials")
DATA_URL = os.getenv("DUBAI_PULSE_INCIDENTS_URL",
                     "https://api.dubaipulse.gov.ae/open/dubai-police/dp_traffic_incidents-open-api")

_cache: dict = {"at": 0.0, "rows": []}


def enabled() -> bool:
    return bool(config.DUBAI_PULSE_KEY and config.DUBAI_PULSE_SECRET)


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def fetch() -> list[dict]:
    if not enabled():
        return []
    if time.time() - _cache["at"] < 600:
        return _cache["rows"]
    try:
        with httpx.Client(timeout=20, headers={"User-Agent": config.USER_AGENT}) as c:
            tok = c.post(TOKEN_URL, data={"client_id": config.DUBAI_PULSE_KEY,
                                          "client_secret": config.DUBAI_PULSE_SECRET}).json()["access_token"]
            r = c.get(DATA_URL, headers={"Authorization": f"Bearer {tok}"}, params={"limit": 2000})
            r.raise_for_status()
            body = r.json()
            raw = body.get("results") or body.get("result", {}).get("records") or body if isinstance(body, list) else []
        rows = []
        for it in raw:
            try:
                rows.append({
                    "lat": float(it.get("acci_x") or it.get("latitude")),
                    "lng": float(it.get("acci_y") or it.get("longitude")),
                    "time": it.get("acci_time") or it.get("incident_time"),
                    "type": it.get("acci_name") or it.get("incident_type") or "",
                })
            except (TypeError, ValueError):
                continue
        _cache.update(at=time.time(), rows=rows)
        return rows
    except Exception as e:
        log.warning("Dubai Pulse incidents unavailable: %s", e)
        return _cache["rows"]


def _parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone(timedelta(hours=4)))
        except ValueError:
            continue
    return None


def near(camera: dict, radius_km: float = 1.0, within: timedelta = timedelta(days=30)) -> list[dict]:
    now = datetime.now(timezone.utc)
    out = []
    for r in fetch():
        t = _parse_time(r["time"])
        if t and now - t > within:
            continue
        if _haversine_km((camera["lat"], camera["lng"]), (r["lat"], r["lng"])) <= radius_km:
            out.append(r)
    return out
