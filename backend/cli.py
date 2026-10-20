"""تشغيل دَرْب AI دفعةً واحدة دون خادم دائم — للاستضافة المجانية (GitHub Actions أو أي مجدول).

    python -m backend.cli daily --regions singapore,phoenix,tucson,yuma,tampa,losangeles,sandiego --site site/

لكل كاميرا: صورة واحدة يوميًا (لقطة «أسبوعية» يوم الإثنين لبناء الاتجاه، وفحص يومي بقية الأيام)،
تحليل بالذكاء الاصطناعي، تحديث المخاطر ودورة حياة المشكلات، ثم بناء الموقع الثابت.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("darb.cli")
ROOT = Path(__file__).resolve().parent.parent
KEEP_IMAGES = int(os.getenv("DARB_KEEP_IMAGES", "10"))  # صور كل كاميرا المحفوظة على القرص (المقاييس تبقى كاملة)


def capture_time(cam, now_utc, pipeline, sources) -> datetime | None:
    """لحظة الالتقاط: ظهر اليوم المحلي للمصادر ذات الأرشيف، والآن للكاميرات الحية (نهارًا فقط)."""
    tz = pipeline.tz(cam)
    local = now_utc.astimezone(tz)
    if sources.supports_history(cam) and cam["source"].get("type") != "demo":
        noon = local.replace(hour=12, minute=0, second=0, microsecond=0)
        return (noon if noon <= local else noon - timedelta(days=1)).astimezone(timezone.utc)
    return now_utc if pipeline.is_daylight(cam, now_utc) else None


def prune_images(config, db) -> int:
    """يحذف الصور الأقدم من آخر KEEP_IMAGES لكل كاميرا لإبقاء التخزين صغيرًا (المقاييس في قاعدة البيانات تبقى)."""
    removed = 0
    for cam in db.query("SELECT DISTINCT camera_id FROM snapshots"):
        rows = db.query("SELECT image_path, annotated_path FROM snapshots WHERE camera_id=? ORDER BY ts DESC", (cam["camera_id"],))
        for r in rows[KEEP_IMAGES:]:
            for rel in (r["image_path"], r["annotated_path"]):
                if rel and (config.DATA_DIR / rel).exists():
                    (config.DATA_DIR / rel).unlink()
                    removed += 1
    return removed


def daily(args) -> int:
    from . import config, db, pipeline, sources
    config.ensure_dirs()
    pipeline.sync_cameras()
    seeded = pipeline.seed_history()  # أول تشغيل: سجل من الأرشيف للمصادر التي تدعمه
    if seeded:
        log.info("seeded %d archive captures", seeded)
    now = datetime.now(timezone.utc)
    done = skipped = failed = 0
    for cam in pipeline.cameras():
        at = capture_time(cam, now, pipeline, sources)
        if at is None:
            log.info("skip %s: night in its region", cam["id"])
            skipped += 1
            continue
        local = at.astimezone(pipeline.tz(cam))
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
        day_end = (local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc).isoformat()
        if db.one("SELECT id FROM snapshots WHERE camera_id=? AND ts>=? AND ts<? AND kind!='manual'", (cam["id"], day_start, day_end)):
            skipped += 1  # التُقطت اليوم مسبقًا
            continue
        kind = "weekly" if local.weekday() == 0 else "sentinel"
        r = pipeline.run_capture(cam["id"], kind, at, n_frames=1, interval=0)
        if r.get("ok"):
            done += 1
            log.info("%s %s -> CI %s", kind, cam["id"], r.get("condition_index"))
        else:
            failed += 1
            log.warning("%s failed: %s", cam["id"], r.get("error") or r.get("quality"))
    log.info("captured=%d skipped=%d failed=%d pruned_images=%d", done, skipped, failed, prune_images(config, db))

    if args.site:
        site = Path(args.site)
        env = {**os.environ}
        subprocess.run([sys.executable, str(ROOT / "tools" / "export_static.py"), str(site)], check=True, env=env)
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_static.py"), str(site), args.leaflet_css], check=True, env=env)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="python -m backend.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily", help="صورة واحدة لكل كاميرا + تحليل + بناء الموقع")
    d.add_argument("--regions", help="المناطق (يتجاوز DARB_REGIONS)")
    d.add_argument("--site", help="مجلد إخراج الموقع الثابت")
    d.add_argument("--leaflet-css", default=str(ROOT / "tools" / "leaflet.css"))
    args = p.parse_args()
    if args.regions:
        os.environ["DARB_REGIONS"] = args.regions  # قبل استيراد config
    os.environ.setdefault("DARB_CONFIRM_RECAPTURE", "0")
    os.environ.setdefault("DARB_SCHEDULER", "0")
    return daily(args)


if __name__ == "__main__":
    raise SystemExit(main())
