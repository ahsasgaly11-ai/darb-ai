"""تنزيل نماذج الذكاء الاصطناعي لعيوب الطرق إلى models/.

    python -m backend.models          # تنزيل
    python -m backend.models --onnx   # + نسخة للمتصفح: ONNX مضغوطة 8-بت (~10 م.ب) لتحليل النماذج بالكاميرا لحظيًا

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


def export_onnx(force: bool = False) -> list[str]:
    """ONNX (640×640) ثم تكميم ديناميكي للأوزان إلى 8-بت: الحجم ربع الأصل والنتائج مطابقة تقريبًا
    (قورنت على صور كاميرات حقيقية). تُشغَّل في المتصفح عبر onnxruntime-web."""
    import json
    import shutil

    from onnxruntime.quantization import QuantType, quantize_dynamic
    from ultralytics import YOLO

    out, manifest = [], []
    for _, _, local, lic in MODELS:
        pt = config.MODELS_DIR / local
        q8 = pt.with_suffix(".q8.onnx")
        if not pt.exists():
            continue
        if force or not q8.exists():
            model = YOLO(str(pt))
            onnx = model.export(format="onnx", imgsz=640, opset=17, simplify=True, dynamic=False)
            quantize_dynamic(onnx, str(q8), weight_type=QuantType.QUInt8)
            if str(onnx) != str(q8):
                shutil.os.remove(onnx)
        names = YOLO(str(pt)).names
        manifest.append({"file": q8.name, "license": lic, "imgsz": 640, "names": [names[i] for i in sorted(names)]})
        out.append(str(q8))
    (config.MODELS_DIR / "browser-models.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    return out


if __name__ == "__main__":
    print("\n".join(download(force="--force" in sys.argv)))
    if "--onnx" in sys.argv:
        print("\n".join(export_onnx(force="--force" in sys.argv)))
