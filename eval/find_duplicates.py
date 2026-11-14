"""Find near-duplicate images across train, public and private test.

Only image files are read (never the question/answer JSON of any split), so
the private test stays unseen. Each image gets two 64-bit perceptual hashes:

* pHash: 32x32 greyscale -> 2-D DCT -> top-left 8x8 above its median
* dHash: 9x8 greyscale -> horizontal gradient signs

Two images are near-duplicates when either rule holds (Hamming distances, of 64):

* pHash <= 10 and dHash <= 14   resized / recompressed / watermarked copies
* pHash <= 16 and dHash <= 7    the same photo re-cropped slightly

Pairs checked by eye and found to be different images are listed in
NOT_DUPLICATES. Groups are the connected components of the relation. Heavier
crops, mirror images and different photos of the same scene may be missed.

    .venv/bin/python eval/find_duplicates.py            # writes data/splits/duplicates.json
    .venv/bin/python eval/find_duplicates.py --report   # also prints near misses
"""

from __future__ import annotations

import argparse
import json
import os
from itertools import combinations
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATASET = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural")) / "dataset"
SPLITS = {
    "train": DATASET / "train data" / "train_images",
    "public": DATASET / "public_test data" / "public_test_images",
    "private": DATASET / "private_test data (post submission)" / "private_test_images",
}
OUT = ROOT / "data" / "splits" / "duplicates.json"

RULES = [(10, 14), (16, 7)]  # (max pHash distance, max dHash distance)

# Reviewed by eye (train/public images only): isolated pictograms on a white
# background whose hashes collide although the signs differ.
NOT_DUPLICATES = {
    frozenset({"train:train_1_23", "train:train_2_31"}),
    frozenset({"train:train_1_23", "train:train_2_38"}),
}


def _dct_matrix(n: int) -> np.ndarray:
    k = np.arange(n)
    m = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n))
    m[0] /= np.sqrt(2)
    return m * np.sqrt(2 / n)


_D32 = _dct_matrix(32)


def phash(img: Image.Image) -> int:
    a = np.asarray(img.convert("L").resize((32, 32), Image.LANCZOS), dtype=np.float64)
    d = _D32 @ a @ _D32.T
    low = d[:8, :8].flatten()
    bits = low > np.median(low[1:])
    return int("".join("1" if b else "0" for b in bits), 2)


def dhash(img: Image.Image) -> int:
    a = np.asarray(img.convert("L").resize((9, 8), Image.LANCZOS), dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def load() -> list[dict]:
    items = []
    for split, folder in SPLITS.items():
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            with Image.open(p) as im:
                items.append({"split": split, "image_id": p.stem,
                              "phash": phash(im), "dhash": dhash(im)})
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print near misses too")
    args = ap.parse_args()

    items = load()
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    pairs, near = [], []
    for i, j in combinations(range(len(items)), 2):
        dp = hamming(items[i]["phash"], items[j]["phash"])
        dd = hamming(items[i]["dhash"], items[j]["dhash"])
        key = frozenset({f"{items[i]['split']}:{items[i]['image_id']}",
                         f"{items[j]['split']}:{items[j]['image_id']}"})
        if key in NOT_DUPLICATES:
            continue
        if any(dp <= pm and dd <= dm for pm, dm in RULES):
            pairs.append((i, j, dp, dd))
            parent[find(i)] = find(j)
        elif dp <= 18 and dd <= 20:
            near.append((i, j, dp, dd))

    comps: dict[int, list[int]] = {}
    for i in range(len(items)):
        comps.setdefault(find(i), []).append(i)
    groups = []
    for members in comps.values():
        if len(members) < 2:
            continue
        ms = set(members)
        dists = [(dp, dd) for i, j, dp, dd in pairs if i in ms and j in ms]
        groups.append({
            "images": sorted(({"split": items[i]["split"], "image_id": items[i]["image_id"]}
                              for i in members), key=lambda x: (x["split"], x["image_id"])),
            "splits": sorted({items[i]["split"] for i in members}),
            "max_phash_distance": max(d[0] for d in dists),
            "max_dhash_distance": max(d[1] for d in dists),
        })
    groups.sort(key=lambda g: (-len(g["splits"]), g["images"][0]["image_id"]))
    cross = [g for g in groups if len(g["splits"]) > 1]

    def dup_ids(split: str, others: set[str]) -> list[str]:
        return sorted({im["image_id"] for g in cross for im in g["images"]
                       if im["split"] == split and set(g["splits"]) & others})

    out = {
        "method": "pHash (DCT 8x8 of 32x32 grey) and dHash (9x8 grey); near-duplicate "
                  "when (pHash <= 10 and dHash <= 14) or (pHash <= 16 and dHash <= 7), of 64 "
                  "bits, minus reviewed false positives; groups = connected components",
        "not_duplicates_reviewed": sorted(sorted(p) for p in NOT_DUPLICATES),
        "counts": {s: sum(1 for it in items if it["split"] == s) for s in SPLITS},
        "groups": groups,
        "cross_split_groups": len(cross),
        # Image ids to leave out when reporting scores "without duplicated images".
        "duplicated_with_train": {
            "public": dup_ids("public", {"train"}),
            "private": dup_ids("private", {"train"}),
        },
        "duplicated_public_private": {
            "public": dup_ids("public", {"private"}),
            "private": dup_ids("private", {"public"}),
        },
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"{len(items)} images, {len(groups)} groups, {len(cross)} across splits -> "
          f"{OUT.relative_to(ROOT)}")
    for g in cross:
        names = ", ".join(f"{im['split']}:{im['image_id']}" for im in g["images"])
        print(f"  [{g['max_phash_distance']:2d}/{g['max_dhash_distance']:2d}] {names}")
    if args.report:
        print("near misses (not grouped):")
        for i, j, dp, dd in sorted(near, key=lambda t: t[2] + t[3]):
            print(f"  [{dp:2d}/{dd:2d}] {items[i]['split']}:{items[i]['image_id']}  "
                  f"{items[j]['split']}:{items[j]['image_id']}")


if __name__ == "__main__":
    main()
