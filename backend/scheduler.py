"""المجدول: التقاط أسبوعي كامل لكل كاميرا (لبناء الاتجاه الزمني والتنبؤ) + فحص سريع دوري
(افتراضيًا كل 24 ساعة) لرصد المشاكل المفاجئة بين اللقطات الأسبوعية + متابعة الحوادث كل 10 دقائق.

لماذا أسبوعي؟ تدهور الرصف عملية بطيئة (أسابيع إلى أشهر)، واللقطة الأسبوعية تعطي نقاطًا كافية
لتقدير الميل دون تراكم بيانات لا فائدة منها؛ أما الحفر المفاجئة والانهيارات فيلتقطها الفحص اليومي.
يمكن تعديل الجدول من متغيرات البيئة أو لكل كاميرا عبر meta.schedule.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import config, pipeline

log = logging.getLogger("darb.scheduler")
_sched: BackgroundScheduler | None = None


def _run_all(kind: str, region: str | None = None) -> None:
    for cam in pipeline.cameras(region=region):
        if kind == "sentinel" and cam["source"].get("type") != "demo" and not pipeline.is_daylight(cam):
            continue
        try:
            r = pipeline.run_capture(cam["id"], kind)
            log.info("%s %s -> %s", kind, cam["id"], r.get("condition_index", r.get("error")))
        except Exception:
            log.exception("capture job failed for %s", cam["id"])


def start() -> BackgroundScheduler:
    global _sched
    if _sched:
        return _sched
    _sched = BackgroundScheduler(timezone=config.TIMEZONE)
    for region in config.REGION_KEYS:  # الالتقاط الأسبوعي بالتوقيت المحلي لكل منطقة (نهارًا)
        _sched.add_job(_run_all, CronTrigger(day_of_week=config.WEEKLY_DAY, hour=config.WEEKLY_HOUR, minute=0,
                                             timezone=config.tz_of(region)),
                       args=["weekly", region], id=f"weekly-{region}", max_instances=1, coalesce=True,
                       misfire_grace_time=6 * 3600)
    if config.SENTINEL_HOURS >= 24:
        for region in config.REGION_KEYS:  # الفحص اليومي في موعد الالتقاط الأسبوعي نفسه (ثبات الإضاءة) بقية أيام الأسبوع
            _sched.add_job(_run_all, CronTrigger(day_of_week="tue-sun" if config.WEEKLY_DAY == "mon" else "*",
                                                 hour=config.WEEKLY_HOUR, minute=0, timezone=config.tz_of(region)),
                           args=["sentinel", region], id=f"sentinel-{region}", max_instances=1, coalesce=True)
    elif config.SENTINEL_HOURS > 0:
        _sched.add_job(_run_all, IntervalTrigger(hours=config.SENTINEL_HOURS), args=["sentinel"], id="sentinel",
                       max_instances=1, coalesce=True)
    _sched.add_job(pipeline.check_incidents, IntervalTrigger(minutes=10), id="incidents", max_instances=1, coalesce=True)

    def followup(cam_id: str) -> None:
        _sched.add_job(pipeline.run_capture, DateTrigger(datetime.now().astimezone() + timedelta(minutes=config.FOLLOWUP_MINUTES)),
                       args=[cam_id, "sentinel"], id=f"followup-{cam_id}", replace_existing=True)
    pipeline.followup_hook = followup
    _sched.start()
    return _sched


def jobs() -> list[dict]:
    if not _sched:
        return []
    return [{"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None} for j in _sched.get_jobs()]


def stop() -> None:
    global _sched
    if _sched:
        _sched.shutdown(wait=False)
        _sched = None
