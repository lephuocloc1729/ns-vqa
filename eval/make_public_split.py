"""Split the public test 50/50 by image into public-dev and public-holdout.

Questions that share an image stay on the same side. Only ids and image ids are
read, so running this does not expose question text. Output:
data/splits/public_split.json. Re-running with the same seed gives the same split.

    .venv/bin/python eval/make_public_split.py
"""

from __future__ import annotations

import json
import os
import random
from collections import defaultdict
from pathlib import Path

SEED = 20261114
ROOT = Path(__file__).resolve().parent.parent
DATASET = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
PUBLIC = DATASET / "dataset" / "public_test data" / "vlsp_2025_public_test.json"
OUT = ROOT / "data" / "splits" / "public_split.json"


def main() -> None:
    rows = json.loads(PUBLIC.read_text(encoding="utf-8"))
    by_image: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_image[r["image_id"]].append(r["id"])
    images = sorted(by_image)
    random.Random(SEED).shuffle(images)
    half = len(images) // 2
    dev_imgs, hold_imgs = sorted(images[:half]), sorted(images[half:])

    def ids(imgs: list[str]) -> list[str]:
        return sorted((q for i in imgs for q in by_image[i]), key=lambda q: int(q.split("_")[-1]))

    split = {
        "seed": SEED,
        "source": "dataset/public_test data/vlsp_2025_public_test.json",
        "method": "shuffle sorted image ids with random.Random(seed); first half -> dev",
        "public_dev": {"images": dev_imgs, "questions": ids(dev_imgs)},
        "public_holdout": {"images": hold_imgs, "questions": ids(hold_imgs)},
    }
    OUT.write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")
    print(f"images {len(dev_imgs)}/{len(hold_imgs)}, "
          f"questions {len(split['public_dev']['questions'])}/"
          f"{len(split['public_holdout']['questions'])} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
