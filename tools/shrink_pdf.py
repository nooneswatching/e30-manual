#!/usr/bin/env python3
"""Shrink a scanned PDF by re-encoding each page as a JPEG image at a given resolution.

Typical result: a 200+ MB scan becomes 30-80 MB. Any existing text layer is dropped (the OCR
pipeline rebuilds it), so only use this on scans, not on born-digital PDFs.

    python tools/shrink_pdf.py manuals/big.pdf            # writes manuals/big-small.pdf at 200 dpi
    python tools/shrink_pdf.py manuals/big.pdf --dpi 250 --quality 60 --replace
"""
import argparse
import io
import os
from pathlib import Path

import pymupdf
from PIL import Image

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("pdf")
ap.add_argument("--dpi", type=int, default=200)
ap.add_argument("--quality", type=int, default=55, help="JPEG quality 1-95 (default 55)")
ap.add_argument("--gray", action="store_true", help="convert pages to grayscale (smaller; fine for text)")
ap.add_argument("--replace", action="store_true", help="overwrite the original file")
args = ap.parse_args()

src = Path(args.pdf)
out = src if args.replace else src.with_name(f"{src.stem}-small.pdf")
tmp = out.with_suffix(".tmp.pdf")
doc = pymupdf.open(src)
new = pymupdf.open()
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=args.dpi, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    if args.gray:
        img = img.convert("L")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=args.quality, optimize=True, progressive=True)
    p = new.new_page(width=page.rect.width, height=page.rect.height)
    p.insert_image(p.rect, stream=buf.getvalue())
    if (i + 1) % 25 == 0 or i + 1 == doc.page_count:
        print(f"  {i + 1}/{doc.page_count} pages", flush=True)
new.save(tmp, garbage=4, deflate=True)
new.close()
doc.close()
os.replace(tmp, out)
print(f"{src.name}: {src.stat().st_size / 1e6:.0f} MB -> {out.name}: {out.stat().st_size / 1e6:.0f} MB")
