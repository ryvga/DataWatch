from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from docx import Document
from pypdf import PdfReader


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("—", "-").replace("–", "-").replace("’", "'")
    return re.sub(r"\s+", " ", value).strip().lower()


docx_path = Path(sys.argv[1])
pdf_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])

doc = Document(docx_path)
targets: list[tuple[str, str]] = []
for paragraph in doc.paragraphs:
    text = paragraph.text.strip()
    if not text:
        continue
    style = paragraph.style.name if paragraph.style else ""
    if style.startswith("Heading"):
        targets.append((text, normalize(text)))
    elif style == "Caption":
        match = re.match(r"((?:Figure|Tableau) \d+\.\d+)", text)
        if match:
            targets.append((match.group(1), normalize(match.group(1))))

raw_pages = [page.extract_text() or "" for page in PdfReader(pdf_path).pages]
pages = [normalize(text) for text in raw_pages]
page_lines = [[normalize(line) for line in text.splitlines() if normalize(line)] for text in raw_pages]
intro_needle = normalize("INTRODUCTION GÉNÉRALE")
intro_pages = [number for number, text in enumerate(pages, start=1) if intro_needle in text]
body_start = max(intro_pages)
result: dict[str, int | str] = {}
for label, needle in targets:
    is_front = re.match(r"^(?:[IVX]+\.|V?I{0,3}\. Liste)", label) is not None
    search_pages = range(body_start - 1, 0, -1) if is_front else range(body_start, len(pages) + 1)
    for page_number in search_pages:
        exact_line = needle in page_lines[page_number - 1]
        broad_match = len(needle) > 35 and needle in pages[page_number - 1]
        caption_match = label.startswith(("Figure ", "Tableau ")) and any(line.startswith(needle) for line in page_lines[page_number - 1])
        if exact_line or broad_match or caption_match:
            result[label] = page_number
            break

# Convert physical PDF pages to the report's numbering systems. The cover is
# unnumbered; front matter starts at PDF page 2; the body starts at the first
# page containing INTRODUCTION GÉNÉRALE.
for key, value in list(result.items()):
    physical = int(value)
    if physical >= body_start:
        result[key] = physical - body_start + 1
    elif physical > 1:
        roman = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]
        result[key] = roman[physical - 2]

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(f"Mapped {len(result)} entries; body starts on physical page {body_start}.")
