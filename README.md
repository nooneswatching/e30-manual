# E30 Manual

Scanned BMW E30 manuals turned into a searchable, browsable web site, plus a RealOEM-style parts
catalogue with clickable exploded diagrams. Everything is static: Python builds the data, the site
is plain HTML/JS that can be hosted on GitHub Pages or any web server.

## What you get

* **OCR of scanned PDFs** with tesseract: page images, text, and word positions. Rotated scans
  are detected and straightened. PDFs that already have a text layer are used as-is.
* **Table of contents** from PDF bookmarks or from BMW repair-code headings
  (`34 11 100 Replacing front brake pads`), grouped by repair group (11 Engine, 34 Brakes, …).
* **Full-text search** across all manuals, with matches highlighted on the scanned page image
  and in the OCR text. Part numbers and repair codes are searchable with or without spaces.
* **Parts catalogue**: main groups → diagrams → parts table, numbered hotspots on the drawing,
  reverse lookup (every diagram a part number appears in), description search, and a built-in
  hotspot editor. Parts groups link to the matching workshop manual sections.

## Quick start

```
# 1. Install tesseract: apt install tesseract-ocr   |   brew install tesseract   |   choco install tesseract
pip install -r requirements.txt

# 2. Put PDFs in manuals/ (see manuals/README.md for titles, TOC overrides and big-file tips)

# 3. Build and preview
python tools/build.py          # OCR (cached per page; first run takes a few seconds per page)
python tools/serve.py          # http://localhost:8000
```

Useful flags: `python tools/build_manuals.py --pages 1-20` for a quick test,
`--force-ocr` to ignore a bad existing text layer, `--lang eng+deu` for German pages.

## Publishing on GitHub Pages

1. Repository **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Push to `main`. The workflow in `.github/workflows/build-and-deploy.yml` installs tesseract,
   OCRs the manuals (results are cached between runs), compiles the parts catalogue and deploys `site/`.

GitHub rejects files over 100 MB; `python tools/shrink_pdf.py manuals/big.pdf` usually brings a
scan well under that, `tools/split_pdf.py` splits it, and Git LFS is also supported (the workflow
only downloads LFS files when the OCR cache misses).

## Layout

```
manuals/     scanned PDFs (+ optional sidecar .json per PDF)
parts/       parts catalogue source: catalog.json, diagrams/*.json, images/
tools/       build_manuals.py (OCR), build_parts.py, build.py, serve.py,
             shrink_pdf.py, split_pdf.py, import_parts_pdf.py (ETK scan → draft diagrams)
site/        the web app; site/data/ is generated and not committed
build/cache  per-page OCR cache keyed on the PDF's hash (not committed)
```

The manuals are copyrighted by their publishers; keep the repository private unless you have the
right to redistribute them.
