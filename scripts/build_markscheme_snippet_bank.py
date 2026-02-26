#!/usr/bin/env python3
import html
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "assets" / "data"
OUT_DIR = ROOT / "assets" / "question_snippets" / "markschemes"

DPI = 180
SCALE = DPI / 72.0


def sh(cmd):
    return subprocess.run(cmd, check=True, text=True, capture_output=True).stdout


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_")


def parse_bbox_pages(xml_text: str):
    pages = []
    for pm in re.finditer(r'<page\s+width="([\d.]+)"\s+height="([\d.]+)">(.*?)</page>', xml_text, flags=re.S):
        width = float(pm.group(1))
        height = float(pm.group(2))
        body = pm.group(3)
        words = []
        for wm in re.finditer(
            r'<word\s+xMin="([\d.]+)"\s+yMin="([\d.]+)"\s+xMax="([\d.]+)"\s+yMax="([\d.]+)">(.*?)</word>',
            body,
            flags=re.S,
        ):
            text = html.unescape(wm.group(5)).strip()
            if not text:
                continue
            words.append(
                {
                    "xMin": float(wm.group(1)),
                    "yMin": float(wm.group(2)),
                    "xMax": float(wm.group(3)),
                    "yMax": float(wm.group(4)),
                    "text": text,
                }
            )
        pages.append({"width": width, "height": height, "words": words})
    return pages


def question_locations(pages):
    def has_answer_pattern(page_words, y_ref, qn):
        line_words = []
        for w in page_words:
            if abs(w["yMin"] - y_ref) <= 5.5:
                line_words.append(w)
        if not line_words:
            return False
        line_words.sort(key=lambda w: w["xMin"])
        line = " ".join(w["text"] for w in line_words)
        if re.search(rf"\b{qn}\b\s+[ABCD]\b", line):
            return True
        if re.search(rf"\b{qn}\b.*\b[ABCD]\b.*\b1\b", line):
            return True
        return False

    cand = {i: [] for i in range(1, 41)}
    for p_idx, p in enumerate(pages, start=1):
        for w in p["words"]:
            if not re.fullmatch(r"\d{1,2}", w["text"]):
                continue
            n = int(w["text"])
            if not (1 <= n <= 40):
                continue
            if w["xMin"] > 90:
                continue
            if w["yMin"] < 35 or w["yMin"] > p["height"] - 45:
                continue
            if not has_answer_pattern(p["words"], w["yMin"], n):
                continue
            cand[n].append((p_idx, w["yMin"]))

    out = {}
    prev_page, prev_y = 1, 0.0
    for n in range(1, 41):
        options = sorted(cand[n], key=lambda x: (x[0], x[1]))
        best = None
        for p_idx, y in options:
            if p_idx < prev_page:
                continue
            if p_idx == prev_page and y <= prev_y + 1.5:
                continue
            best = (p_idx, y)
            break
        if best is None and options:
            best = options[0]
        if best:
            out[n] = best
            prev_page, prev_y = best
    return out


def crop_question(pdf_path: Path, page_no: int, y0: float, y1: float, out_png: Path, page_width: float):
    y0 = max(0, y0)
    y1 = max(y0 + 30, y1)
    x_px = 0
    y_px = int(y0 * SCALE)
    w_px = int(page_width * SCALE)
    h_px = max(120, int((y1 - y0) * SCALE))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    prefix = out_png.with_suffix("")
    cmd = [
        "pdftoppm",
        "-f",
        str(page_no),
        "-singlefile",
        "-png",
        "-r",
        str(DPI),
        "-x",
        str(x_px),
        "-y",
        str(y_px),
        "-W",
        str(w_px),
        "-H",
        str(h_px),
        str(pdf_path),
        str(prefix),
    ]
    subprocess.run(cmd, check=True)


def infer_ms_path(qp_path: Path):
    n1 = qp_path.name.replace(" QP - ", " MS - ")
    candidate = qp_path.with_name(n1)
    if candidate.exists():
        return candidate
    n2 = qp_path.name.replace("QP - ", "MS - ")
    candidate = qp_path.with_name(n2)
    if candidate.exists():
        return candidate
    n3 = re.sub(r"\bQP\b", "MS", qp_path.name)
    candidate = qp_path.with_name(n3)
    if candidate.exists():
        return candidate
    return None


def build():
    qb = json.loads((DATA / "question-bank.json").read_text(encoding="utf-8"))
    questions = qb.get("questions", [])
    papers = {}
    for q in questions:
        rel_qp = q.get("paper")
        if not rel_qp:
            continue
        n = q.get("number")
        if not n:
            continue
        papers.setdefault(rel_qp, set()).add(int(n))

    lookup = {}
    generated = 0

    for rel_qp, qnums in papers.items():
        qp_path = ROOT / rel_qp
        if not qp_path.exists():
            continue
        ms_path = infer_ms_path(qp_path)
        if ms_path is None or not ms_path.exists():
            continue
        xml_text = sh(["pdftotext", "-bbox-layout", str(ms_path), "-"])
        pages = parse_bbox_pages(xml_text)
        if not pages:
            continue
        qloc = question_locations(pages)
        ordered = sorted(qnums)
        detected = sorted(qloc.keys())
        for n in ordered:
            if n not in qloc:
                continue
            p_no, y_start = qloc[n]
            p = pages[p_no - 1]
            y_end = p["height"] - 35
            next_candidates = [x for x in detected if x > n]
            if next_candidates:
                nxt = next_candidates[0]
                np_no, ny = qloc[nxt]
                if np_no == p_no and ny > y_start + 20:
                    y_end = ny - 16

            paper_slug = slug(ms_path.stem)
            out_png = OUT_DIR / slug(ms_path.parent.name) / f"{paper_slug}_q{n:02d}.png"
            try:
                crop_question(ms_path, p_no, y_start - 8, y_end, out_png, p["width"])
                key = f"{rel_qp}::{n}"
                lookup[key] = str(out_png.relative_to(ROOT)).replace("\\", "/")
                generated += 1
            except subprocess.CalledProcessError:
                continue

    out = {"generated": generated, "lookup": lookup}
    (DATA / "question-ms-image-bank.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (DATA / "question-ms-image-bank.js").write_text(
        "window.SOLVERLIFE_MS_IMAGE_BANK = " + json.dumps(out, ensure_ascii=True, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(f"Generated markscheme snippets: {generated}")


if __name__ == "__main__":
    build()
