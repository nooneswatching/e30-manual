#!/usr/bin/env python3
"""Split a PDF that is too large for GitHub (>100 MB) into parts of at most N pages.

    python tools/split_pdf.py manuals/big-manual.pdf 150
"""
import sys
from pathlib import Path

import pymupdf

src = Path(sys.argv[1])
per = int(sys.argv[2]) if len(sys.argv) > 2 else 150
doc = pymupdf.open(src)
for i, start in enumerate(range(0, doc.page_count, per), 1):
    part = pymupdf.open()
    part.insert_pdf(doc, from_page=start, to_page=min(start + per, doc.page_count) - 1)
    out = src.with_name(f"{src.stem}-part{i:02d}.pdf")
    part.save(out, garbage=3, deflate=True)
    print(out, part.page_count, "pages")
print("Now delete the original and add a sidecar .json per part if you want custom titles.")
