#!/usr/bin/env python3
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "assets/data"


def run_tesseract_text(image_path: Path) -> str:
    proc = subprocess.run(
        ["tesseract", str(image_path), "stdout", "--oem", "1", "--psm", "6"],
        check=True,
        text=True,
        capture_output=True,
    )
    txt = proc.stdout
    txt = txt.replace("\x0c", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def build():
    img_bank_path = DATA / "question-image-bank.json"
    if not img_bank_path.exists():
        raise SystemExit("Missing assets/data/question-image-bank.json. Run build_image_snippet_bank.py first.")

    img_bank = json.loads(img_bank_path.read_text(encoding="utf-8"))
    lookup = img_bank.get("lookup", {})

    out_lookup = {}
    done = 0

    for key, rel_img in lookup.items():
        img_path = ROOT / rel_img
        if not img_path.exists():
            continue
        try:
            txt = run_tesseract_text(img_path)
        except subprocess.CalledProcessError:
            txt = ""

        out_lookup[key] = {
            "image": rel_img,
            "ocrText": txt,
            "hasText": bool(txt),
        }
        done += 1

    out = {
        "generated": done,
        "lookup": out_lookup,
    }

    (DATA / "question-ocr-bank.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (DATA / "question-ocr-bank.js").write_text(
        "window.SOLVERLIFE_OCR_BANK = " + json.dumps(out, ensure_ascii=True, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(f"Generated OCR entries: {done}")


if __name__ == "__main__":
    build()
