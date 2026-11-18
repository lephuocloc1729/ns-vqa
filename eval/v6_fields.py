"""Scene v6 fields on set T (owner, 2026-11-17): a hand-label sheet and a score from the same paid
set-T run. The rule, fixed before the run: a field (signals, markings, arrows) below 70% precision is
switched off in kb/v6_fields_47.yaml, so its rules give unknown.

    .venv/bin/python eval/v6_fields.py sheet                       # writes the label sheet (image ids only)
    .venv/bin/python eval/v6_fields.py score <set-T v6 run .jsonl> # precision / recall per field

The sheet is data/annotations/gold_v6_fields/labels_v6_fields.yaml: one row per set-T image. The
owner fills `signals`, `markings` and `r411` by looking at each photo and sets `checked: true`; only
checked rows are scored. `r411_in_gold` flags the images whose gold sign labels have an R.411 board.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

SHEET = ROOT / "data" / "annotations" / "gold_v6_fields" / "labels_v6_fields.yaml"
PRECISION_FLOOR = 0.70
FIELDS = ("signals", "markings", "arrows")


def sheet(path: Path = SHEET) -> Path:
    from eval import gold_signs as gs
    from eval import perception_eval as pe
    if path.exists():
        raise SystemExit(f"{path} exists; it holds the owner's labels")
    gold = pe.gold_rows()
    rows = []
    for i in gs.set_t_images():
        r411 = any((s.get("code") or "").startswith("R.411") for s in gold[i]["signs"])
        rows.append({"image_id": i, "checked": False, "r411_in_gold": r411,
                     "signals": [], "markings": [], "r411": []})
    head = ("# Scene v6 field labels for set T (owner fills by hand; image ids only, no model output).\n"
            "# signals: [{colour: red|yellow|green|off, arrow: none|left|straight|right}] for lamps lit and facing the road\n"
            "# markings: [{kind: center|lane_line|edge|hatched|stop_line, pattern: solid|dashed|double_solid|solid_dashed|dashed_solid}]\n"
            "# r411: [{lane: 1, directions: [straight, left, right, u_turn, slight_left, slight_right]}] for an R.411 board\n"
            "# Leave a list empty when the photo shows none; set checked: true when the row is done.\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(head + yaml.safe_dump({"images": rows}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _items(field: str, scene: dict | None, label: dict | None) -> set[tuple]:
    """Comparable items of one field, from a scene dump (label None) or a label row."""
    if label is not None:
        if field == "signals":
            return {(g["colour"], g.get("arrow", "none")) for g in label.get("signals") or []}
        if field == "markings":
            return {(m["kind"], m.get("pattern")) for m in label.get("markings") or []}
        return {(r["lane"], tuple(sorted(r["directions"]))) for r in label.get("r411") or []}
    scene = scene or {}
    if field == "signals":
        return {(g["colour"], g.get("arrow", "none")) for g in scene.get("signals") or [] if g.get("kind", "vehicle") == "vehicle"}
    if field == "markings":
        return {(m["kind"], m.get("pattern")) for m in (scene.get("road") or {}).get("markings") or []}
    return {(r["lane"], tuple(sorted(r["directions"]))) for s in scene.get("signs") or []
            if (s.get("code") or "").startswith("R.411") for r in s.get("lanes") or [] if r.get("directions")}


def score(run_rows: list[dict], labels: list[dict]) -> dict:
    checked = {r["image_id"]: r for r in labels if r.get("checked")}
    out = {}
    for f in FIELDS:
        tp = fp = fn = skipped_incomplete = 0
        for row in run_rows:
            lab = checked.get(row["image_id"])
            if lab is None:
                continue
            if f == "arrows" and lab.get("r411_complete") is False:
                skipped_incomplete += 1
                continue
            pred, gold = _items(f, row.get("scene"), None), _items(f, None, lab)
            tp, fp, fn = tp + len(pred & gold), fp + len(pred - gold), fn + len(gold - pred)
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        decision = ("no prediction to judge: keep on, too few to measure" if prec is None
                    else "switch off (below 70% precision)" if prec < PRECISION_FLOOR else "keep on")
        out[f] = {"tp": tp, "fp": fp, "fn": fn, "skipped_incomplete": skipped_incomplete, "precision": prec and round(prec, 3),
                  "recall": rec and round(rec, 3), "decision": decision}
    return {"checked_images": len(checked), "fields": out,
            "switch_off": [f for f, v in out.items() if v["decision"].startswith("switch off")]}


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("sheet")
    s = sp.add_parser("score")
    s.add_argument("run", type=Path)
    s.add_argument("--labels", type=Path, default=SHEET)
    a = ap.parse_args()
    if a.cmd == "sheet":
        print(sheet())
        return
    rows = [json.loads(x) for x in a.run.read_text(encoding="utf-8").splitlines()[1:] if x.strip()]
    labels = yaml.safe_load(a.labels.read_text(encoding="utf-8"))["images"]
    print(json.dumps(score(rows, labels), indent=2))


if __name__ == "__main__":
    main()
