"""تنزيل نماذج الذكاء الاصطناعي لعيوب الطرق إلى models/.

    python -m backend.models

النماذج (مدرّبة على RDD2022، مستضافة على Hugging Face):
  - rezzzq/yolo12s-road-damage-rdd2022 — رخصة MIT، تضيف فئة «Repair» للترقيعات (مفيدة لمرحلة «بعد»).
  - dronefreak/rdd2022-yolov8s — رخصة AGPL-3.0.
تشغيلها يتطلب مكتبة ultralytics (رخصة AGPL-3.0) — راجع شروط الرخصة قبل النشر التجاري.
"""
from __future__ import annotations

import sys

import httpx

from . import config

MODELS = [
    ("rezzzq/yolo12s-road-damage-rdd2022", "yolo12s_RDD2022_best.pt", "rdd2022-yolo12s.pt", "MIT"),
    ("dronefreak/rdd2022-yolov8s", "best.pt", "rdd2022-yolov8s.pt", "AGPL-3.0"),
]


def download(force: bool = False) -> list[str]:
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    done = []
    for repo, remote, local, lic in MODELS:
        dest = config.MODELS_DIR / local
        if dest.exists() and not force:
            done.append(str(dest))
            continue
        url = f"https://huggingface.co/{repo}/resolve/main/{remote}"
        print(f"↓ {repo} ({lic}) → {dest}")
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
            tmp.rename(dest)
        done.append(str(dest))
    return done


if __name__ == "__main__":
    print("\n".join(download(force="--force" in sys.argv)))
