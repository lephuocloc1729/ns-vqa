"""The naturalized dataset as an annotation layer over the original VLSP 2025 MLQA-TSR release.

`VLSP2025-MLQA-Natural/` is built from VLSP's data: its images and `law_db` are VLSP's, unchanged, and its
questions come from VLSP with the author's edits. Only the natural answers, the edits and the review are
the author's own. So the dataset itself is not redistributed. Instead:

- `export` (the author) writes the **layer**: the author's text files only (the split JSONs with the
  natural answers, `README.md`, `manifest.json`, `review.json`; `provenance.json` only with
  `--with-provenance`, since it quotes VLSP's original samples), plus `layer.json`, which lists the
  sha256 of every file of the finished dataset, including the VLSP images and `law_db` files the layer
  leaves out.
- `build` (anyone with the VLSP release) takes the layer and the VLSP release, finds each VLSP file by its
  name and checks its sha256, copies it, and checks every file of the result against `layer.json`. The
  result is `VLSP2025-MLQA-Natural/` exactly as the author's (without `provenance.json` unless the layer
  has it), so the README's reproduction steps work unchanged.

Neither command prints a question, an answer or an image name: counts only. The layer is written outside
the repository only (it holds dataset text, which is never committed).

    .venv/bin/python tools/naturalized_layer.py export --out ~/naturalized_layer [--splits train,public_test] [--with-provenance]
    .venv/bin/python tools/naturalized_layer.py build --layer ~/naturalized_layer --vlsp <VLSP release folder> --out VLSP2025-MLQA-Natural

Offline authoring tool, not inference code.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural"))
SCHEMA = 1
LAYER_FILE = "layer.json"
SPLITS = {   # split -> (its folder under dataset/, its JSON file, its image folder)
    "train": ("train data", "vlsp_2025_train.json", "train_images"),
    "public_test": ("public_test data", "vlsp_2025_public_test.json", "public_test_images"),
    "private_test": ("private_test data (post submission)", "vlsp_2025_private_test.json", "private_test_images"),
}
ROOT_TEXT = ("README.md", "manifest.json", "review.json")       # the author's own files at the root
PROVENANCE = "provenance.json"                                   # quotes VLSP's original samples
LAW_DB = "dataset/law_db"
SKIP = {".DS_Store"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def json_sha256(path: Path) -> str:
    """The sha256 of a JSON file's content, whatever its formatting (VLSP copies differ in whitespace)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def _files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.name not in SKIP)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- export (the author)

def export(dataset: Path, out: Path, *, splits: tuple[str, ...] = tuple(SPLITS), with_provenance: bool = False,
           repo: Path = ROOT) -> dict:
    """Write the layer for `splits` into `out` (a new folder outside the repository)."""
    dataset, out = Path(dataset), Path(out)
    if bad := sorted(set(splits) - set(SPLITS)):
        raise SystemExit(f"unknown split(s): {', '.join(bad)}; the splits are {', '.join(SPLITS)}")
    if _inside(out, repo):
        raise SystemExit("the layer holds dataset text: write it outside the repository")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    text, vlsp = {}, {}
    for name in ROOT_TEXT + ((PROVENANCE,) if with_provenance else ()):
        if (dataset / name).exists():
            text[name] = dataset / name
    for split in splits:
        folder, js, images = SPLITS[split]
        text[f"dataset/{folder}/{js}"] = dataset / "dataset" / folder / js
        for p in _files(dataset / "dataset" / folder / images):
            vlsp[p.relative_to(dataset).as_posix()] = p
    for p in _files(dataset / LAW_DB):
        rel = p.relative_to(dataset).as_posix()
        (vlsp if p.suffix.lower() in (".jpg", ".jpeg", ".png") or p.name == "vlsp2025_law.json" else text)[rel] = p
    if missing := [k for k, p in text.items() if not p.exists()]:
        raise SystemExit(f"{len(missing)} expected file(s) are missing from the dataset")
    out.mkdir(parents=True, exist_ok=True)
    for rel, p in text.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out / rel)
    record = {"schema": SCHEMA, "what": "the author's annotation layer over VLSP 2025 MLQA-TSR (tools/naturalized_layer.py)",
              "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "splits": list(splits), "with_provenance": with_provenance,
              "text_files": {k: sha256(p) for k, p in sorted(text.items())},
              "vlsp_files": {k: sha256(p) for k, p in sorted(vlsp.items())},
              # JSON files from VLSP: their content hash too, since copies of the release differ in formatting
              "vlsp_json_content": {k: json_sha256(p) for k, p in sorted(vlsp.items()) if p.suffix == ".json"}}
    (out / LAYER_FILE).write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {"splits": list(splits), "text_files": len(record["text_files"]), "vlsp_files": len(record["vlsp_files"])}
    print(f"layer -> {out}: {summary}")                                  # counts only
    return summary


# ---------------------------------------------------------------- build (anyone with the VLSP release)

def _index(vlsp: Path) -> dict[str, list[Path]]:
    by_name: dict[str, list[Path]] = {}
    for p in _files(vlsp):
        by_name.setdefault(p.name, []).append(p)
    return by_name


def build(layer: Path, vlsp: Path, out: Path) -> dict:
    """Rebuild the naturalized dataset in `out` from the layer and the VLSP release."""
    layer, vlsp, out = Path(layer), Path(vlsp), Path(out)
    rec = json.loads((layer / LAYER_FILE).read_text(encoding="utf-8"))
    if rec.get("schema") != SCHEMA:
        raise SystemExit(f"{LAYER_FILE} has schema {rec.get('schema')!r}; this tool reads schema {SCHEMA}")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    if bad := [k for k, h in rec["text_files"].items() if not (layer / k).exists() or sha256(layer / k) != h]:
        raise SystemExit(f"{len(bad)} file(s) of the layer are missing or changed: get a fresh copy of the layer")
    index = _index(vlsp)
    content = rec.get("vlsp_json_content", {})
    found, missing, mismatched, reformatted = {}, 0, 0, set()
    for rel, h in rec["vlsp_files"].items():
        cands = index.get(Path(rel).name, [])
        hit = next((p for p in cands if sha256(p) == h), None)
        if hit is None and rel in content:          # the same JSON content, formatted differently
            hit = next((p for p in cands if p.suffix == ".json" and json_sha256(p) == content[rel]), None)
            if hit is not None:
                reformatted.add(rel)
        if hit is not None:
            found[rel] = hit
        elif cands:
            mismatched += 1
        else:
            missing += 1
    if missing or mismatched:
        raise SystemExit(f"the VLSP release lacks {missing} file(s) and has {mismatched} with different content, "
                         f"of {len(rec['vlsp_files'])} needed: use the original VLSP 2025 MLQA-TSR release, "
                         "including the private test images if the layer has the private test")
    out.mkdir(parents=True, exist_ok=True)
    for rel in rec["text_files"]:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(layer / rel, out / rel)
    for rel, p in found.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out / rel)
    want = {**rec["text_files"], **rec["vlsp_files"]}
    have = {p.relative_to(out).as_posix(): (sha256(p) if p.relative_to(out).as_posix() not in reformatted
                                            else rec["vlsp_files"][p.relative_to(out).as_posix()])
            for p in _files(out)}
    if have != want or any(json_sha256(out / r) != content[r] for r in reformatted):
        raise SystemExit("the rebuilt dataset does not match layer.json")
    summary = {"splits": rec["splits"], "files": len(have), "with_provenance": rec.get("with_provenance", False),
               "same_content_other_formatting": len(reformatted)}
    print(f"dataset -> {out}: {summary}; every file matches layer.json")   # counts only
    return summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="the author: write the layer")
    e.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--splits", default=",".join(SPLITS), help="comma-separated: train,public_test,private_test")
    e.add_argument("--with-provenance", action="store_true", help="also include provenance.json (quotes VLSP's samples)")
    b = sub.add_parser("build", help="rebuild the dataset from the layer and the VLSP release")
    b.add_argument("--layer", type=Path, required=True)
    b.add_argument("--vlsp", type=Path, required=True, help="the original VLSP 2025 MLQA-TSR release (any layout)")
    b.add_argument("--out", type=Path, default=ROOT / "VLSP2025-MLQA-Natural")
    a = ap.parse_args(argv)
    if a.cmd == "export":
        export(a.dataset, a.out, splits=tuple(s.strip() for s in a.splits.split(",") if s.strip()),
               with_provenance=a.with_provenance)
    else:
        build(a.layer, a.vlsp, a.out)


if __name__ == "__main__":
    sys.exit(main())
