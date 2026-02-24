#!/usr/bin/env python3
import json
import random
import re
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAPERS = [
    {
        "subject": "biology",
        "topic_pool": ["cells", "genetics", "ecology", "human-biology", "enzymes"],
        "qp": ROOT / "assets/papers/biology/Biology - Paper 1/November 2021 (v2) QP - Paper 1 CAIE Biology IGCSE.pdf",
        "ms": ROOT / "assets/papers/biology/Biology - Paper 1/November 2021 (v2) MS - Paper 1 CAIE Biology IGCSE.pdf",
    },
    {
        "subject": "chemistry",
        "topic_pool": ["bonding", "stoichiometry", "acids-bases", "organic", "electrolysis"],
        "qp": ROOT / "assets/papers/chemistry/Chemistry - Paper 2/November 2021 (v1) QP - Paper 2 CAIE Chemistry IGCSE.pdf",
        "ms": ROOT / "assets/papers/chemistry/Chemistry - Paper 2/November 2021 (v1) MS - Paper 2 CAIE Chemistry IGCSE.pdf",
    },
    {
        "subject": "physics",
        "topic_pool": ["forces", "electricity", "waves", "energy", "motion"],
        "qp": ROOT / "assets/papers/physics/Physics - Paper 2/November 2021 (v2) QP - Paper 2 CAIE Physics IGCSE.pdf",
        "ms": ROOT / "assets/papers/physics/Physics - Paper 2/November 2021 (v2) MS - Paper 2 CAIE Physics IGCSE.pdf",
    },
]

MIN_YEAR = 2016

NOISE_PATTERNS = [
    r"www\.root19\.com",
    r"\+91\s*-\s*9969\s*353\s*391",
    r"©\s*UCLES",
    r"\[Turn over\]",
    r"Page \d+ of \d+",
    r"PMT",
    r"0620/\d+",
    r"0610/\d+",
    r"0625/\d+",
]


def run_pdftotext_layout(pdf_path: Path) -> str:
    proc = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=True,
        text=True,
        capture_output=True,
    )
    return proc.stdout


def squash_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_noise(text: str) -> str:
    out = text
    for pat in NOISE_PATTERNS:
        out = re.sub(pat, " ", out, flags=re.I)
    return out


def parse_answers(ms_text: str):
    ans = {}
    for q, a in re.findall(r"(?m)^\s*(\d{1,2})\s+([ABCD])\b", ms_text):
        qn = int(q)
        if 1 <= qn <= 40:
            ans[qn] = a
    return ans


def extract_option_map(block: str):
    markers = list(re.finditer(r"(?m)^\s*([ABCD])\s+", block))
    if len(markers) < 4:
        return None

    options = {}
    for i, m in enumerate(markers):
        letter = m.group(1)
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(block)
        options[letter] = squash_whitespace(strip_noise(block[start:end]))

    if not all(options.get(k) for k in ["A", "B", "C", "D"]):
        return None
    return options


def parse_questions(qp_text: str):
    questions = {}
    blocks = re.findall(r"(?ms)^\s*(\d{1,2})\s+(.*?)(?=^\s*\d{1,2}\s+|\Z)", qp_text)

    for qnum_str, body in blocks:
        qnum = int(qnum_str)
        if not (1 <= qnum <= 40):
            continue
        if qnum in questions:
            continue

        body = strip_noise(body)
        opts = extract_option_map(body)
        if not opts:
            continue

        first_opt = re.search(r"(?m)^\s*A\s+", body)
        if not first_opt:
            continue
        stem = squash_whitespace(strip_noise(body[:first_opt.start()]))

        if len(stem) < 12:
            continue

        questions[qnum] = {
            "question": stem,
            "opts": [opts["A"], opts["B"], opts["C"], opts["D"]],
        }

    return questions


def extract_year(path: Path):
    m = re.search(r"(19|20)\d{2}", path.name)
    if not m:
        return None
    return int(m.group(0))


def build():
    random.seed(7)
    bank = []

    for paper in PAPERS:
        year = extract_year(paper["qp"])
        if year is not None and year < MIN_YEAR:
            continue

        qp_text = run_pdftotext_layout(paper["qp"])
        ms_text = run_pdftotext_layout(paper["ms"])

        answers = parse_answers(ms_text)
        questions = parse_questions(qp_text)

        for n in range(1, 41):
            if n not in questions or n not in answers:
                continue
            ans_letter = answers[n]
            ans_idx = ord(ans_letter) - ord("A")
            opts = questions[n]["opts"]
            bank.append(
                {
                    "subject": paper["subject"],
                    "topic": paper["topic_pool"][(n - 1) % len(paper["topic_pool"])],
                    "q": questions[n]["question"],
                    "opts": opts,
                    "a": ans_idx,
                    "why": f"Official mark scheme answer: {ans_letter}. This option matches the key.",
                    "paper": str(paper["qp"].relative_to(ROOT)),
                    "year": year,
                    "number": n,
                }
            )

    out = {
        "generatedAt": datetime.now().isoformat(),
        "count": len(bank),
        "questions": bank,
    }

    out_path = ROOT / "assets/data/question-bank.json"
    out_path.write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")
    js_path = ROOT / "assets/data/question-bank.js"
    js_path.write_text("window.SOLVERLIFE_BANK = " + json.dumps(out, ensure_ascii=True, indent=2) + ";\n", encoding="utf-8")
    print(f"Wrote {len(bank)} questions -> {out_path}")


if __name__ == "__main__":
    build()
