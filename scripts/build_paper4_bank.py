#!/usr/bin/env python3
import html
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "assets" / "data"
OUT_IMG_DIR = ROOT / "assets" / "question_snippets" / "paper4"

DPI = 180
SCALE = DPI / 72.0
MIN_YEAR = 2016

PAPERS = [
    {
        "subject": "biology",
        "topic_pool": ["cells", "transport", "enzymes", "genetics", "ecology"],
        "qp": ROOT / "assets/papers4/biology/Biology - Paper 4/November 2021 (v2) QP - Paper 4 CAIE Biology IGCSE.pdf",
        "ms": ROOT / "assets/papers4/biology/Biology - Paper 4/November 2021 (v2) MS - Paper 4 CAIE Biology IGCSE.pdf",
    },
    {
        "subject": "chemistry",
        "topic_pool": ["stoichiometry", "bonding", "acids-bases", "organic", "electrolysis"],
        "qp": ROOT / "assets/papers4/chemistry/Chemistry - Paper 4/November 2021 (v3) QP - Paper 4 CAIE Chemistry IGCSE.pdf",
        "ms": ROOT / "assets/papers4/chemistry/Chemistry - Paper 4/November 2021 (v3) MS - Paper 4 CAIE Chemistry IGCSE.pdf",
    },
    {
        "subject": "physics",
        "topic_pool": ["motion", "forces", "electricity", "waves", "energy"],
        "qp": ROOT / "assets/papers4/physics/Physics - Paper 4/November 2021 (v3) QP - Paper 4 CAIE Physics IGCSE.pdf",
        "ms": ROOT / "assets/papers4/physics/Physics - Paper 4/November 2021 (v3) MS - Paper 4 CAIE Physics IGCSE.pdf",
    },
]

NOISE_PATTERNS = [
    r"\[Turn[^\]]*\]?",
    r"\bover\s*\[Turn\b",
    r"Page \d+ of \d+",
    r"©\s*UCLES",
    r"\bBLANK\s+PAGE\b",
    r"\bPermission to reproduce items\b.*",
    r"\breasonable effort has been made by the publisher\b.*",
    r"PMT",
    r"www\.root19\.com",
    r"\+91\s*-\s*9969\s*353\s*391",
    r"\b0\d{3}/\d{2}(?:/[A-Z]{1,3}/\d{2,4})?\b",
    r"\b20\d{2}\s+0\d{3}/\d{2}/[A-Z]{1,3}/\d{2,4}\b",
    r"\b(?:19|20)\d{2}\s*/[A-Z]/[A-Z]/\d{2,4}\b",
    r"\b/[A-Z]/[A-Z]/\d{2,4}\b",
    r"\s{2,}",
]


def sh(cmd):
    return subprocess.run(cmd, check=True, text=True, capture_output=True).stdout


def extract_year(path: Path):
    m = re.search(r"(19|20)\d{2}", path.name)
    return int(m.group(0)) if m else None


def clean_text(text: str) -> str:
    out = text
    for pat in NOISE_PATTERNS:
        out = re.sub(pat, " ", out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def looks_invalid_question(text: str) -> bool:
    t = clean_text(text or "").lower()
    if len(t) < 12:
        return True
    if "blank page" in t:
        return True
    if "permission to reproduce items" in t:
        return True
    if re.search(r"\b0\d{3}/\d{2}(?:/[a-z]{1,3}/\d{2,4})?\b", t):
        return True
    if re.search(r"\b(?:19|20)\d{2}\s*/[a-z]/[a-z]/\d{2,4}\b", t):
        return True
    if len(re.sub(r"[^a-z]+", "", t)) < 8:
        return True
    return False


def pdftotext_layout(path: Path) -> str:
    return sh(["pdftotext", "-layout", str(path), "-"])


def parse_q_blocks(layout_text: str):
    blocks = {}
    for qn, body in re.findall(r"(?ms)^\s*(\d{1,2})\s+(.*?)(?=^\s*\d{1,2}\s+|\Z)", layout_text):
        n = int(qn)
        if n < 1 or n > 40:
            continue
        blocks[n] = body.strip()
    return blocks


def parse_subparts(block: str):
    raw = clean_text(block)
    marks = [int(x) for x in re.findall(r"\[(\d{1,2})\]", block)]
    total_marks = sum(marks) if marks else 1
    chunks = []
    matches = list(re.finditer(r"\(\s*([a-z])\s*\)", block, flags=re.I))
    if not matches:
        return [{"label": "main", "text": raw, "marks": total_marks}]

    for idx, m in enumerate(matches):
        label = m.group(1).lower()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(block)
        part_raw = block[start:end]
        part_text = clean_text(part_raw)
        part_marks_list = [int(x) for x in re.findall(r"\[(\d{1,2})\]", part_raw)]
        part_marks = sum(part_marks_list) if part_marks_list else 1
        if len(part_text) >= 8:
            chunks.append({"label": label, "text": part_text, "marks": part_marks})

    if not chunks:
        return [{"label": "main", "text": raw, "marks": total_marks}]
    return chunks


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
    cand = {i: [] for i in range(1, 41)}
    for p_idx, p in enumerate(pages, start=1):
        for w in p["words"]:
            if not re.fullmatch(r"\d{1,2}", w["text"]):
                continue
            n = int(w["text"])
            if not (1 <= n <= 40):
                continue
            if w["xMin"] > 100:
                continue
            if w["yMin"] < 40 or w["yMin"] > p["height"] - 50:
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


def crop(pdf_path: Path, page_no: int, y0: float, y1: float, out_png: Path, page_width: float):
    y0 = max(0, y0)
    y1 = max(y0 + 40, y1)
    x_px = 0
    y_px = int(y0 * SCALE)
    w_px = int(page_width * SCALE)
    h_px = max(180, int((y1 - y0) * SCALE))
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


def build_snippet_lookup(pdf_path: Path, stem_slug: str, kind: str):
    xml_text = sh(["pdftotext", "-bbox-layout", str(pdf_path), "-"])
    pages = parse_bbox_pages(xml_text)
    if not pages:
        return {}
    qloc = question_locations(pages)
    qnums = sorted(qloc.keys())
    lookup = {}
    for i, n in enumerate(qnums):
        p_no, y_start = qloc[n]
        p = pages[p_no - 1]
        y_end = p["height"] - 30
        if i + 1 < len(qnums):
            next_n = qnums[i + 1]
            np_no, ny = qloc[next_n]
            if np_no == p_no and ny > y_start + 20:
                y_end = ny - 6
        out_png = OUT_IMG_DIR / stem_slug / kind / f"q{n:02d}.png"
        try:
            crop(pdf_path, p_no, y_start - 8, y_end, out_png, p["width"])
            lookup[n] = str(out_png.relative_to(ROOT)).replace("\\", "/")
        except subprocess.CalledProcessError:
            continue
    return lookup


def build():
    out_questions = []
    for paper in PAPERS:
        qp = paper["qp"]
        ms = paper["ms"]
        if not qp.exists() or not ms.exists():
            continue
        year = extract_year(qp)
        if year is not None and year < MIN_YEAR:
            continue

        q_layout = pdftotext_layout(qp)
        m_layout = pdftotext_layout(ms)
        q_blocks = parse_q_blocks(q_layout)
        m_blocks = parse_q_blocks(m_layout)

        paper_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", qp.stem).strip("_")
        q_snippets = build_snippet_lookup(qp, paper_slug, "qp")
        m_snippets = build_snippet_lookup(ms, paper_slug, "ms")

        for qn in sorted(q_blocks.keys()):
            block = q_blocks.get(qn, "")
            if looks_invalid_question(block):
                continue
            ms_block = clean_text(m_blocks.get(qn, ""))
            parts = parse_subparts(block)
            parts = [p for p in parts if not looks_invalid_question(p.get("text", ""))]
            if not parts:
                continue
            out_questions.append(
                {
                    "paperType": "paper4",
                    "subject": paper["subject"],
                    "topic": paper["topic_pool"][(qn - 1) % len(paper["topic_pool"])],
                    "year": year,
                    "number": qn,
                    "paper": str(qp.relative_to(ROOT)).replace("\\", "/"),
                    "questionText": clean_text(block),
                    "markschemeText": ms_block,
                    "parts": parts,
                    "questionImage": q_snippets.get(qn, ""),
                    "markschemeImage": m_snippets.get(qn, ""),
                    "totalMarks": sum([max(1, int(p.get("marks", 1))) for p in parts]) if parts else 1,
                }
            )

    out = {
        "generatedAt": datetime.now().isoformat(),
        "count": len(out_questions),
        "questions": out_questions,
    }
    (DATA_DIR / "paper4-bank.json").write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")
    (DATA_DIR / "paper4-bank.js").write_text(
        "window.SOLVERLIFE_PAPER4_BANK = " + json.dumps(out, ensure_ascii=True, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(out_questions)} Paper 4 questions")


if __name__ == "__main__":
    build()
