#!/usr/bin/env python3
"""Draft parts-diagram JSON files from a scanned BMW parts catalogue (ETK) PDF.

Each selected page becomes one diagram: the page image goes to parts/images/ and every
BMW part number found by OCR (11 digits, e.g. "11 42 1 730 389") becomes an item, with
the text on the same OCR line used as the description. Callout hotspots are NOT detected;
place them with the in-browser editor (open the diagram and press "Edit hotspots").

    python tools/import_parts_pdf.py manuals/etk-scan.pdf --pages 12-40 --group 11
"""
import argparse
import io
import json
import re
import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build_manuals import _ocr_image, parse_pages, slugify  # noqa: E402

PART_RE = re.compile(r"\b(\d{2})\s?(\d{2})\s?(\d)\s?(\d{3})\s?(\d{3})\b")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--pages", help="pages to import, e.g. 12-40 (default: all)")
    ap.add_argument("--group", help="BMW main group for these diagrams, e.g. 11")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--lang", default="eng")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    doc = pymupdf.open(pdf)
    stem = slugify(pdf.stem)
    img_dir = ROOT / "parts" / "images"
    dia_dir = ROOT / "parts" / "diagrams"
    img_dir.mkdir(parents=True, exist_ok=True)
    dia_dir.mkdir(parents=True, exist_ok=True)

    for idx in parse_pages(args.pages, doc.page_count):
        page = doc[idx]
        pix = page.get_pixmap(dpi=args.dpi, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text, _ = _ocr_image(img, args.lang, 3)
        did = f"{(args.group or 'xx')}_{stem}_p{idx + 1}"
        out_json = dia_dir / f"{did}.json"
        if out_json.exists() and not args.overwrite:
            print(f"skip page {idx + 1}: {out_json.name} exists (use --overwrite)")
            continue
        items = []
        seen = set()
        title = ""
        for ln in text.split("\n"):
            m = PART_RE.search(ln)
            if not m:
                if not title and len(ln.strip()) > 5:
                    title = ln.strip()[:80]
                continue
            num = "".join(m.groups())
            if num in seen:
                continue
            seen.add(num)
            desc = (ln[:m.start()] + " " + ln[m.end():]).strip(" .-|:")
            nm = re.match(r"^(\d{1,3})\b\s*(.*)$", desc)
            n = int(nm.group(1)) if nm else None
            if nm:
                desc = nm.group(2)
            items.append({"n": n, "part": f"{num[0:2]} {num[2:4]} {num[4]} {num[5:8]} {num[8:]}",
                          "desc": desc.strip(), "qty": None, "notes": ""})
        img_name = f"{did}.webp"
        view = img.convert("RGB")
        if view.width > 2000:
            view = view.resize((2000, round(view.height * 2000 / view.width)), Image.LANCZOS)
        view.save(img_dir / img_name, "WEBP", quality=80)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump({"id": did, "title": title or f"{pdf.stem} page {idx + 1}", "group": args.group or "",
                       "image": img_name, "source": f"{pdf.name} p.{idx + 1}", "notes": "",
                       "callouts": [], "items": items}, f, ensure_ascii=False, indent=1)
        print(f"page {idx + 1}: {len(items)} part numbers -> {out_json.name}")
    print("Next: review the JSON files, add diagram ids to parts/catalog.json, then run tools/build_parts.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
