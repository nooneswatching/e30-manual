# parts/ — RealOEM-style parts catalogue

The catalogue is plain JSON plus images, so it can be edited by hand, generated from a scanned
BMW parts catalogue (ETK), or assembled from any other source.

```
parts/
  catalog.json            main groups (11 Engine, 34 Brakes, …) and the diagrams in each
  diagrams/11_0450.json   one file per diagram
  images/11_0450.png      the exploded-view drawing (png, jpg, webp or svg)
```

Run `python tools/build_parts.py` (or `tools/build.py`) after editing; warnings list missing
images, bad coordinates and diagrams not referenced by the catalog.

## catalog.json

```json
{
  "vehicle": { "name": "BMW 3 Series (E30)", "years": "1982-1994" },
  "groups": [
    { "id": "11", "name": "Engine", "diagrams": ["11_0450", "11_0500"] },
    { "id": "34", "name": "Brakes",  "diagrams": ["34_0210"] }
  ]
}
```

Group ids are BMW main-group numbers (see `tools/bmw_groups.py`), which lets the site cross-link a
parts group with the workshop manual sections for the same group. A diagram file whose id is not
listed in the catalog is still shown, under the group in its own `group` field. Remove the
`"sample": true` line once you have replaced the placeholder data.

## diagrams/<id>.json

```json
{
  "id": "11_0450",
  "title": "Lubrication system / Oil filter",
  "group": "11",
  "image": "11_0450.png",
  "source": "ETK 1991 p. 112",
  "notes": "Free text shown under the title",
  "callouts": [ { "n": 1, "x": 0.27, "y": 0.23 }, { "n": 2, "x": 0.46, "y": 0.16 } ],
  "items": [
    { "n": 1, "part": "11 42 1 730 389", "desc": "Oil filter element kit", "qty": 1, "notes": "", "models": ["325i", "325is"] },
    { "n": 2, "part": "11 42 1 000 000", "desc": "Oil filter housing", "qty": 1 }
  ]
}
```

* `callouts` place the numbered hotspots on the image. `x` and `y` are fractions of the image
  width and height (0..1), so the same file works at any display size.
* `items` are the rows of the parts table. `n` links a row to its callout. Part numbers can be
  written with or without spaces; they are normalised for search and reverse lookup.
* The same part number in several diagrams is automatically cross-referenced on the part's page.

## Placing hotspots without editing numbers by hand

Open a diagram on the site and press **Edit hotspots**: click a row in the table, then click the
spot on the drawing; drag to adjust; double-click a hotspot to delete it. **Copy diagram JSON**
gives you the complete file to paste over `parts/diagrams/<id>.json`. Rebuild and the hotspots
are live.

## Importing a scanned parts catalogue

If one of your PDFs is a BMW ETK / parts microfiche scan:

```
python tools/import_parts_pdf.py manuals/etk.pdf --pages 40-75 --group 11
```

Every page becomes a draft diagram in `parts/diagrams/` with the page image in `parts/images/`
and every 11-digit BMW part number found by OCR as an item (the text on the same line becomes the
description). Then fix descriptions, add the diagram ids to `catalog.json`, and place the hotspots
with the editor.
