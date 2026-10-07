# manuals/

Drop your scanned E30 manuals here as PDFs. Each PDF becomes one manual on the site.

```
manuals/
  bentley-e30-service-manual.pdf
  bentley-e30-service-manual.json      <- optional settings for that PDF (same name, .json)
  electrical-troubleshooting-1989.pdf
```

Then build:

```
pip install -r requirements.txt       # once; also needs tesseract (apt install tesseract-ocr / brew install tesseract)
python tools/build.py                 # OCRs every PDF (cached: re-runs only touch new pages)
python tools/serve.py                 # open http://localhost:8000
```

Pushing the PDFs to GitHub triggers the same build in GitHub Actions and publishes the site to GitHub Pages.

## Big files

GitHub refuses single files over 100 MB. Options, in order of convenience:

1. **Shrink the scan**: `python tools/shrink_pdf.py manuals/big.pdf` rewrites the page images as
   200 dpi JPEG (configurable). Scans are usually 2-5x smaller afterwards with no effect on OCR.
2. **Split it**: `python tools/split_pdf.py manuals/big.pdf 150` makes `big-part01.pdf`, `big-part02.pdf`, ...
   Each part becomes its own manual; use sidecar `.json` files to give them titles like "Bentley (sections 11-34)".
3. **Git LFS**: run `git lfs install` and `git lfs track "manuals/*.pdf"` *before* `git add`. The build
   workflow pulls LFS files only when the OCR cache misses, to stay inside the free bandwidth quota.

## Sidecar settings (`<name>.json`)

Every key is optional.

```json
{
  "title": "Bentley E30 Service Manual 1984-1991",
  "type": "workshop",            // workshop | electrical | owners | parts | other (just a label)
  "description": "Shown on the manual's card",
  "page_offset": 12,             // printed page 1 is PDF page 13 (used to show printed page numbers)
  "force_ocr": false,            // true: ignore a bad existing text layer and OCR anyway
  "ocr": { "lang": "eng", "psm": 3, "ocr_dpi": 300, "view_width": 1600, "image_quality": 72, "osd": true },
  "toc": [                       // hand-written table of contents overrides automatic detection
    { "title": "11 Engine", "page": 45, "level": 1 },
    { "title": "11 31 005 Removing and installing camshaft", "page": 61, "level": 2 }
  ]
}
```

Table of contents detection order: sidecar `toc` → PDF bookmarks/outline → heuristics
(BMW repair codes such as `34 11 100 Replacing front brake pads`, "Section 11 - Engine" lines, and
all-caps headings at the top of a page). Titles starting with a two-digit BMW main group number
are grouped under that group (11 Engine, 34 Brakes, 61 Electrical, ...).
