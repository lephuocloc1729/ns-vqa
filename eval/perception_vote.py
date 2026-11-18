"""Phase 4.8 step 2 (a) (owner, 2026-11-18): vote several set-T perception runs per sign. Free.

Takes run files of one configuration (same set, model and prompt; each pass 1 + fallback), and
writes one combined run file whose scene per image is `vqa.perception.vote.vote` over the runs'
scenes, in the order given. `perception_eval.py score` then scores it like any run.

    .venv/bin/python eval/perception_vote.py eval/runs/perception/<a>.jsonl <b>.jsonl <c>.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.perception_eval import RUNS, load_run  # noqa: E402


def combine(paths: list[Path], out_dir: Path = RUNS) -> Path:
    from vqa.kb import load_catalog
    from vqa.perception.vote import vote
    from vqa.schemas import SceneGraph
    runs = [load_run(p) for p in paths]
    heads = [h for h, _ in runs]
    key = lambda h: (h["set"], h["model"], h["prompt_id"], bool(h.get("fallback")))  # noqa: E731
    if len({key(h) for h in heads}) != 1:
        raise SystemExit("the runs differ in set, model, prompt or fallback: " + str([key(h) for h in heads]))
    if len({h["run_id"] for h in heads}) != len(heads):
        raise SystemExit("the same run is given twice")
    by_img = [{r["image_id"]: r for r in rows} for _, rows in runs]
    images = [r["image_id"] for r in runs[0][1]]
    if any(set(b) != set(images) for b in by_img):
        raise SystemExit("the runs cover different images")
    cat = load_catalog()
    run_id = uuid.uuid4().hex[:12]
    h0 = heads[0]
    fam = h0["prompt_id"].split("/")[1].split("@")[0]
    out = out_dir / f"{h0['set']}_{h0['model']}_{fam}+fb+vote{len(paths)}_{run_id}.jsonl"
    head = {**h0, "run_id": run_id, "vote": [h["run_id"] for h in heads]}
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(head, ensure_ascii=False) + "\n")
        for i in images:
            rows = [b[i] for b in by_img]
            scenes = [SceneGraph.model_validate(r["scene"]) for r in rows if r.get("scene")]
            sc = vote(scenes, cat) if scenes else None
            f.write(json.dumps({"image_id": i, "ok": sc is not None, "error": None, "retried": False,
                                "cost_usd": sum(r.get("cost_usd") or 0 for r in rows),
                                "reran": any(r.get("reran") for r in rows), "issues": [],
                                "scene": sc.model_dump(mode="json", by_alias=True) if sc else None},
                               ensure_ascii=False) + "\n")
    print(f"vote of {[h['run_id'] for h in heads]} -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args()
    combine(a.files)


if __name__ == "__main__":
    main()
