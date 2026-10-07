#!/usr/bin/env python3
"""OCR scanned PDF manuals into page images, text, and a search corpus for the web app.

Usage:
    python tools/build_manuals.py                 # build everything in manuals/
    python tools/build_manuals.py --pages 1-20    # quick test on the first 20 pages
    python tools/build_manuals.py --force-ocr     # ignore any embedded text layer

Every PDF in manuals/ becomes one manual. An optional sidecar `manuals/<name>.json`
can override the title, type, table of contents and OCR settings (see manuals/README.md).

Results are cached in build/cache/ keyed on the PDF's content hash, so re-running
only OCRs pages that have not been processed before.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from bmw_groups import MAIN_GROUPS, group_name  # noqa: E402

DEFAULTS = {
    "lang": "eng",
    "psm": 3,
    "ocr_dpi": 300,
    "view_width": 1600,   # max pixel width of the page image shown in the browser
    "image_quality": 72,
    "osd": True,          # detect and fix rotated scans
}

# "11 31 005 Removing and installing camshaft"
REPAIR_CODE_RE = re.compile(r"^\s*(\d{2})\s?(\d{2})\s?(\d{3})\s+([A-Za-z(][^\n]{2,90})$")
# "Section 11 - Engine", "GROUP 34 BRAKES"
SECTION_RE = re.compile(r"^\s*(?:section|group|chapter)\s+(\d{1,3})\s*[-:.–]?\s*([A-Za-z][^\n]{2,80})$", re.I)
# An all-caps heading line near the top of a page
CAPS_RE = re.compile(r"^[A-Z][A-Z0-9 ,/&\-()']{5,70}$")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "manual"


def file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def parse_pages(spec: str | None, count: int) -> list[int]:
    if not spec:
        return list(range(count))
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.update(range(int(a) - 1, min(int(b), count)))
        elif part:
            pages.add(int(part) - 1)
    return sorted(p for p in pages if 0 <= p < count)


def load_sidecar(pdf: Path) -> dict:
    sidecar = pdf.with_suffix(".json")
    if sidecar.exists():
        with open(sidecar, encoding="utf-8") as f:
            return json.load(f)
    return {}


# --------------------------------------------------------------------------------------
# Per-page worker (runs in a subprocess)
# --------------------------------------------------------------------------------------

def _osd_rotation(img) -> int:
    """Return degrees the image must be rotated clockwise to be upright, or 0."""
    import pytesseract

    try:
        osd = pytesseract.image_to_osd(img, config="--psm 0")
    except Exception:
        return 0
    m = re.search(r"Rotate:\s*(\d+)", osd)
    rot = int(m.group(1)) if m else 0
    conf = re.search(r"Orientation confidence:\s*([\d.]+)", osd)
    if rot and conf and float(conf.group(1)) < 1.0:
        return 0
    return rot if rot in (90, 180, 270) else 0


def _ocr_image(img, lang: str, psm: int) -> tuple[str, list]:
    """OCR a PIL image. Returns (text, words) where words are [text, x0, y0, x1, y1] in 0..1."""
    import pytesseract

    data = pytesseract.image_to_data(
        img, lang=lang, config=f"--psm {psm}", output_type=pytesseract.Output.DICT
    )
    W, H = img.size
    words: list = []
    lines: dict[tuple, list[str]] = {}
    order: list[tuple] = []
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(txt)
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append([txt, round(x / W, 4), round(y / H, 4), round((x + w) / W, 4), round((y + h) / H, 4)])

    # Rebuild readable text: blank line between paragraphs/blocks.
    out: list[str] = []
    prev = None
    for key in order:
        if prev is not None and key[:2] != prev[:2]:
            out.append("")
        out.append(" ".join(lines[key]))
        prev = key
    return "\n".join(out).strip(), words


def _text_layer(page) -> tuple[str, list]:
    """Use an existing PDF text layer (born-digital PDF or previously OCR'd scan)."""
    rect = page.rect
    W, H = rect.width or 1, rect.height or 1
    words = []
    for x0, y0, x1, y1, txt, *_ in page.get_text("words"):
        txt = txt.strip()
        if txt:
            words.append([txt, round(x0 / W, 4), round(y0 / H, 4), round(x1 / W, 4), round(y1 / H, 4)])
    text = page.get_text("text").strip()
    return text, words


def process_page(job: dict) -> dict:
    """Render + OCR one page. Executed in a worker process."""
    import pymupdf
    from PIL import Image

    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    pdf, idx, opts = job["pdf"], job["index"], job["opts"]
    cache_file = Path(job["cache_file"])
    img_file = Path(job["img_file"])

    if cache_file.exists() and img_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            rec = json.load(f)
        rec["cached"] = True
        return rec

    doc = pymupdf.open(pdf)
    page = doc[idx]
    rotation = 0
    source = "ocr"

    existing_text = page.get_text("text").strip() if not opts["force_ocr"] else ""
    if len(existing_text) >= 40:
        text, words = _text_layer(page)
        source = "pdf-text"
        pix = page.get_pixmap(dpi=min(opts["ocr_dpi"], 200), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
    else:
        pix = page.get_pixmap(dpi=opts["ocr_dpi"], alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        if opts["osd"]:
            rotation = _osd_rotation(img)
            if rotation:
                img = img.rotate(-rotation, expand=True)
        try:
            text, words = _ocr_image(img, opts["lang"], opts["psm"])
        except Exception as e:  # tesseract hiccup: keep going, note it
            text, words = "", []
            source = f"ocr-failed: {e}"[:120]

    # Page image for the viewer (downscaled, WebP).
    img_file.parent.mkdir(parents=True, exist_ok=True)
    view = img.convert("RGB")
    if view.width > opts["view_width"]:
        scale = opts["view_width"] / view.width
        view = view.resize((opts["view_width"], max(1, round(view.height * scale))), Image.LANCZOS)
    try:
        view.save(img_file, "WEBP", quality=opts["image_quality"], method=4)
    except Exception:
        img_file = img_file.with_suffix(".jpg")
        view.save(img_file, "JPEG", quality=opts["image_quality"], optimize=True)

    rec = {
        "n": idx + 1,
        "w": view.width,
        "h": view.height,
        "img": img_file.name,
        "rotation": rotation,
        "source": source,
        "text": text,
        "words": words,
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    rec["cached"] = False
    return rec


# --------------------------------------------------------------------------------------
# Section / table-of-contents detection
# --------------------------------------------------------------------------------------

def clean_title(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip(" .-_:|")
    t = re.sub(r"[\s.]{3,}\d+$", "", t)  # trailing dot leaders + page number
    return t


def detect_sections(pages: list[dict]) -> list[dict]:
    """Heuristic headings from OCR text when the PDF has no outline."""
    found: list[dict] = []
    for rec in pages:
        text = rec.get("text") or ""
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if not lines:
            continue
        got_code = False
        for ln in lines:
            m = REPAIR_CODE_RE.match(ln)
            if m:
                g, s, n, title = m.groups()
                title = clean_title(title)
                if len(title) < 4 or sum(c.isalpha() for c in title) < 4:
                    continue
                found.append({"title": f"{g} {s} {n} {title}", "page": rec["n"], "group": g, "level": 2})
                got_code = True
                continue
            m = SECTION_RE.match(ln)
            if m and not got_code:
                num, title = m.groups()
                code = num.zfill(2)[:2]
                found.append({"title": f"{num} {clean_title(title)}", "page": rec["n"],
                              "group": code if code in MAIN_GROUPS else None, "level": 1})
                got_code = True
        if not got_code:
            # Fall back to an all-caps heading among the first few lines of the page.
            for ln in lines[:4]:
                cand = clean_title(ln)
                if CAPS_RE.match(cand) and len(cand.split()) >= 2 and sum(c.isalpha() for c in cand) >= 6:
                    found.append({"title": cand, "page": rec["n"], "group": None, "level": 2})
                    break
    # De-duplicate consecutive identical headings (running headers).
    out: list[dict] = []
    for sec in found:
        if out and out[-1]["title"].lower() == sec["title"].lower():
            continue
        out.append(sec)
    # Running page headers that repeat on many pages are noise, drop titles seen > 6 times.
    counts: dict[str, int] = {}
    for sec in out:
        counts[sec["title"].lower()] = counts.get(sec["title"].lower(), 0) + 1
    return [s for s in out if counts[s["title"].lower()] <= 6]


def outline_sections(doc) -> list[dict]:
    toc = []
    for level, title, page in doc.get_toc(simple=True):
        if page < 1:
            continue
        title = clean_title(title)
        m = re.match(r"^(\d{2})\b", title)
        toc.append({"title": title, "page": page, "level": min(level, 3),
                    "group": m.group(1) if m and m.group(1) in MAIN_GROUPS else None})
    return toc


def assign_groups(toc: list[dict]) -> list[dict]:
    """Group sections by BMW main group for the table of contents sidebar."""
    groups: dict[str, dict] = {}
    for sec in toc:
        gid = sec.get("group") or "other"
        if gid not in groups:
            groups[gid] = {"id": gid, "name": group_name(gid) if gid != "other" else "Other sections",
                           "sections": []}
        groups[gid]["sections"].append(sec)
    ordered = sorted(groups.values(), key=lambda g: (g["id"] == "other", g["id"]))
    return ordered


# --------------------------------------------------------------------------------------
# Main build
# --------------------------------------------------------------------------------------

def build_manual(pdf: Path, args, out_root: Path, cache_root: Path) -> dict:
    import pymupdf

    sidecar = load_sidecar(pdf)
    manual_id = sidecar.get("id") or slugify(pdf.stem)
    title = sidecar.get("title") or re.sub(r"[_\-]+", " ", pdf.stem).strip().title()
    opts = dict(DEFAULTS)
    opts.update(sidecar.get("ocr", {}))
    if args.dpi:
        opts["ocr_dpi"] = args.dpi
    if args.lang:
        opts["lang"] = args.lang
    if args.no_osd:
        opts["osd"] = False
    opts["force_ocr"] = bool(args.force_ocr or sidecar.get("force_ocr"))

    digest = file_hash(pdf)
    doc = pymupdf.open(pdf)
    page_count = doc.page_count
    page_indexes = parse_pages(args.pages, page_count)
    outline = outline_sections(doc)
    doc.close()

    # The cache key includes everything that changes OCR output.
    opt_key = hashlib.sha1(json.dumps({k: opts[k] for k in sorted(opts)}, sort_keys=True).encode()).hexdigest()[:8]
    cache_dir = cache_root / f"{digest}-{opt_key}"
    out_dir = out_root / "manuals" / manual_id
    img_dir = out_dir / "img"
    page_dir = out_dir / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)

    jobs = [{
        "pdf": str(pdf), "index": i, "opts": opts,
        "cache_file": str(cache_dir / f"{i + 1}.json"),
        "img_file": str(img_dir / f"{i + 1}.webp"),
    } for i in page_indexes]

    print(f"\n== {title} ({pdf.name}): {len(jobs)} of {page_count} pages, "
          f"{opts['ocr_dpi']} dpi, lang={opts['lang']}, workers={args.workers}")
    t0 = time.time()
    results: dict[int, dict] = {}
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_page, j): j["index"] for j in jobs}
        for fut in as_completed(futures):
            rec = fut.result()
            results[rec["n"]] = rec
            done += 1
            if done % 10 == 0 or done == len(jobs):
                cached = sum(1 for r in results.values() if r.get("cached"))
                print(f"   {done}/{len(jobs)} pages ({cached} from cache) {time.time() - t0:.0f}s", flush=True)

    pages = [results[n] for n in sorted(results)]

    # Per-page JSON for the viewer (text + word boxes).
    for rec in pages:
        with open(page_dir / f"{rec['n']}.json", "w", encoding="utf-8") as f:
            json.dump({k: rec[k] for k in ("n", "w", "h", "img", "text", "words", "source")}, f, ensure_ascii=False)

    # Table of contents: sidecar > PDF outline > heuristics.
    if sidecar.get("toc"):
        toc = []
        for sec in sidecar["toc"]:
            m = re.match(r"^(\d{2})\b", sec["title"])
            toc.append({"title": sec["title"], "page": int(sec["page"]), "level": int(sec.get("level", 1)),
                        "group": sec.get("group") or (m.group(1) if m and m.group(1) in MAIN_GROUPS else None)})
        toc_source = "sidecar"
    elif outline:
        toc, toc_source = outline, "pdf-outline"
    else:
        toc, toc_source = detect_sections(pages), "heuristic"
    toc.sort(key=lambda s: (s["page"], s["level"]))

    # Search corpus: one document per page, tagged with the section in effect.
    search_dir = out_root / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    section_for_page: dict[int, str] = {}
    current = ""
    toc_iter = iter(toc)
    nxt = next(toc_iter, None)
    for rec in pages:
        while nxt and nxt["page"] <= rec["n"]:
            current = nxt["title"]
            nxt = next(toc_iter, None)
        section_for_page[rec["n"]] = current
    docs = [{"id": f"{manual_id}:{rec['n']}", "p": rec["n"], "s": section_for_page[rec["n"]],
             "t": re.sub(r"\s+", " ", rec["text"]).strip()} for rec in pages if rec["text"]]
    with open(search_dir / f"{manual_id}.json", "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False)

    ocr_pages = sum(1 for r in pages if r["source"] == "ocr")
    empty = sum(1 for r in pages if not r["text"])
    print(f"   done in {time.time() - t0:.0f}s: {ocr_pages} OCR'd, {len(pages) - ocr_pages} from text layer, "
          f"{empty} empty, toc={toc_source} ({len(toc)} entries)")

    return {
        "id": manual_id,
        "title": title,
        "type": sidecar.get("type", "workshop"),
        "description": sidecar.get("description", ""),
        "file": pdf.name,
        "pages": page_count,
        "built_pages": [r["n"] for r in pages],
        "page_offset": int(sidecar.get("page_offset", 0)),
        "toc": toc,
        "toc_source": toc_source,
        "groups": assign_groups(toc),
        "search": f"search/{manual_id}.json",
        "hash": digest,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdfs", nargs="*", help="specific PDFs to build (default: all in manuals/)")
    ap.add_argument("--manuals-dir", default=str(ROOT / "manuals"))
    ap.add_argument("--out", default=str(ROOT / "site" / "data"))
    ap.add_argument("--cache", default=str(ROOT / "build" / "cache"))
    ap.add_argument("--pages", help="page range to build, e.g. 1-20 or 5,9,12-14 (for testing)")
    ap.add_argument("--dpi", type=int, help="OCR render resolution (default 300)")
    ap.add_argument("--lang", help="tesseract language(s), e.g. eng or eng+deu")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 0))
    ap.add_argument("--force-ocr", action="store_true", help="OCR even if the PDF already has a text layer")
    ap.add_argument("--no-osd", action="store_true", help="skip rotation detection")
    ap.add_argument("--clean", action="store_true", help="delete generated output for manuals first")
    args = ap.parse_args()

    manuals_dir = Path(args.manuals_dir)
    out_root = Path(args.out)
    cache_root = Path(args.cache)
    pdfs = [Path(p) for p in args.pdfs] if args.pdfs else sorted(manuals_dir.glob("*.pdf"))
    pdfs = [p for p in pdfs if p.exists()]
    if not pdfs:
        print(f"No PDFs found in {manuals_dir}. Drop your scanned manuals there and re-run.")
        # Still write an empty index so the site loads.
        out_root.mkdir(parents=True, exist_ok=True)
        with open(out_root / "manuals.json", "w") as f:
            json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "manuals": []}, f)
        return 0

    if args.clean:
        shutil.rmtree(out_root / "manuals", ignore_errors=True)
        shutil.rmtree(out_root / "search", ignore_errors=True)

    try:
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception as e:
        print(f"ERROR: tesseract is not available ({e}). Install it: apt install tesseract-ocr  /  brew install tesseract")
        return 1

    manuals = [build_manual(pdf, args, out_root, cache_root) for pdf in pdfs]
    out_root.mkdir(parents=True, exist_ok=True)
    with open(out_root / "manuals.json", "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M"), "manuals": manuals}, f, ensure_ascii=False, indent=1)
    print(f"\nWrote {out_root / 'manuals.json'} with {len(manuals)} manual(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
