#!/usr/bin/env python3
"""Compile the parts catalogue (parts/) into site/data/parts/.

Source layout (see parts/README.md):
    parts/catalog.json          main groups -> diagram lists
    parts/diagrams/<id>.json    one file per diagram: image, callouts (hotspots), items (parts)
    parts/images/<file>         diagram images (png/jpg/webp/svg)

Output:
    site/data/parts/index.json  everything the web app needs
    site/data/parts/images/     copied diagram images
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from bmw_groups import group_name  # noqa: E402

PARTS_DIR = ROOT / "parts"
OUT_DIR = ROOT / "site" / "data" / "parts"


def normalize_part(num: str) -> str:
    """'11 42 1 730 389' -> '11421730389'. Non-BMW numbers are upper-cased, spaces removed."""
    return re.sub(r"[\s.\-]", "", str(num)).upper()


def format_part(num: str) -> str:
    n = normalize_part(num)
    if re.fullmatch(r"\d{11}", n):
        return f"{n[0:2]} {n[2:4]} {n[4]} {n[5:8]} {n[8:11]}"
    return num


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    problems: list[str] = []
    catalog = load_json(PARTS_DIR / "catalog.json") if (PARTS_DIR / "catalog.json").exists() else {"groups": []}
    diagrams: dict[str, dict] = {}
    for path in sorted((PARTS_DIR / "diagrams").glob("*.json")):
        d = load_json(path)
        d.setdefault("id", path.stem)
        if d["id"] != path.stem:
            problems.append(f"{path.name}: id '{d['id']}' does not match file name")
        d.setdefault("title", d["id"])
        d.setdefault("callouts", [])
        d.setdefault("items", [])
        d.setdefault("notes", "")
        for c in d["callouts"]:
            for k in ("x", "y"):
                if not (0 <= float(c.get(k, -1)) <= 1):
                    problems.append(f"{path.name}: callout {c.get('n')} has {k} outside 0..1")
        for it in d["items"]:
            if it.get("part"):
                it["part_display"] = format_part(it["part"])
                it["part"] = normalize_part(it["part"])
        diagrams[d["id"]] = d

    # Group tree. Diagrams listed in the catalog keep its order; unlisted ones are appended
    # to the group named in their own "group" field.
    groups: dict[str, dict] = {}
    for g in catalog.get("groups", []):
        gid = str(g["id"])
        groups[gid] = {"id": gid, "name": g.get("name") or group_name(gid), "diagrams": []}
        for did in g.get("diagrams", []):
            if did not in diagrams:
                problems.append(f"catalog.json: group {gid} lists unknown diagram '{did}'")
                continue
            groups[gid]["diagrams"].append(did)
            diagrams[did].setdefault("group", gid)
    for d in diagrams.values():
        gid = str(d.get("group") or d["id"].split("_")[0])
        d["group"] = gid
        groups.setdefault(gid, {"id": gid, "name": group_name(gid), "diagrams": []})
        if d["id"] not in groups[gid]["diagrams"]:
            groups[gid]["diagrams"].append(d["id"])

    # Copy images.
    img_out = OUT_DIR / "images"
    if img_out.exists():
        shutil.rmtree(img_out)
    img_out.mkdir(parents=True)
    for d in diagrams.values():
        if not d.get("image"):
            continue
        src = PARTS_DIR / "images" / d["image"]
        if src.exists():
            shutil.copy2(src, img_out / src.name)
            d["image"] = f"images/{src.name}"
        else:
            problems.append(f"{d['id']}: image '{d['image']}' not found in parts/images/")
            d["image"] = None

    # Reverse index: part number -> where it is used.
    parts: dict[str, dict] = {}
    for d in diagrams.values():
        for it in d["items"]:
            if not it.get("part"):
                continue
            p = parts.setdefault(it["part"], {"part": it["part"], "display": it["part_display"],
                                              "desc": it.get("desc", ""), "uses": []})
            if not p["desc"] and it.get("desc"):
                p["desc"] = it["desc"]
            p["uses"].append({"diagram": d["id"], "n": it.get("n"), "group": d["group"],
                              "qty": it.get("qty"), "notes": it.get("notes", "")})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "vehicle": catalog.get("vehicle", {}),
        "sample": bool(catalog.get("sample", False)),
        "groups": sorted(groups.values(), key=lambda g: g["id"]),
        "diagrams": diagrams,
        "parts": parts,
    }
    with open(OUT_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)

    for p in problems:
        print("WARNING:", p)
    print(f"Parts catalogue: {len(groups)} groups, {len(diagrams)} diagrams, {len(parts)} part numbers "
          f"-> {OUT_DIR / 'index.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
