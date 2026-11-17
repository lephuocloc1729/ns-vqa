"""B6 perception test: guide-board transcription on dev images (phase 4.5 step 1; owner,
2026-11-17). Eval-only; nothing in vqa/ uses it. The test decides whether B6 (guide-sign
content) is worth building.

- **Images:** the 24 dev images in `eval/guide_trial/labels_dev.yaml` (dev is readable).
- **Labels:** the boards transcribed by hand from the images (destinations, distances,
  arrows, speed discs, route plates).
- **The call:** Haiku 5.5, medium, one call per image with `prompts/scene/v5-guide-trial/`
  (pinned by sha256), in two variants:
  - **A:** the photo alone;
  - **B:** the photo plus enlarged crops of the boards the frozen dev run's scene listed
    (I / IE boards and unread rectangular boards), so small text is legible.
  One retry on bad JSON that sends only the error. Raw replies are kept, so rescoring is free.
- **Scores** (pooled over images): entry recall and precision (a label entry matches a read
  entry when their accent-folded texts are at least 0.8 alike), distance accuracy and arrow
  accuracy on matched entries (arrows also scored leniently: slight_left counts as left),
  speed-disc recall, and boards read on the two images with no text.

    .venv/bin/python eval/guide_trial.py estimate
    .venv/bin/python eval/guide_trial.py run --max-spend 0.20
    .venv/bin/python eval/guide_trial.py score <run file>
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import difflib
import hashlib
import io
import json
import re
import sys
import unicodedata
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import gold_signs as gs  # noqa: E402
from eval import two_pass_trial as tp  # noqa: E402
from vqa.llm.client import LLMBadJSON, LLMRefusal, LLMTruncated, parse_json_reply  # noqa: E402
from vqa.llm.pricing import cost_usd  # noqa: E402
from vqa.perception.wire import retry_messages  # noqa: E402

VERSION = "v5-guide-trial"
PROMPT_DIR = ROOT / "prompts" / "scene" / VERSION
LABELS = ROOT / "eval" / "guide_trial" / "labels_dev.yaml"
DEV_RUN = ROOT / "eval" / "runs" / "e2e" / "dev_frozen_13ded0d75451.jsonl"
RUNS = ROOT / "eval" / "runs" / "perception"
MODEL = "claude-haiku-5-5"
PINNED = "c921108016d7b5ed9f7912e8d31b197c9e7a2d04af0df6f9ff9346bdc6e0d562"
MATCH = 0.8
BOARD_CODES = ("I.", "IE.")


# ---------------------------------------------------------------- the prompt

def config() -> dict[str, Any]:
    return yaml.safe_load((PROMPT_DIR / "config.yaml").read_text(encoding="utf-8"))


def system_prompt() -> str:
    spec = (PROMPT_DIR / "spec.md").read_text(encoding="utf-8").strip()
    ex = [json.loads(l) for l in (PROMPT_DIR / "examples.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    shots = "\n\n".join(f"Example ({e['note']}):\n" + json.dumps(e["output"], ensure_ascii=False, separators=(",", ":"))
                        for e in ex)
    return f"{spec}\n\n# Examples\n\n{shots}\n"


def prompt_hash() -> str:
    return hashlib.sha256((system_prompt() + "\n--config--\n" + (PROMPT_DIR / "config.yaml")
                           .read_text(encoding="utf-8")).encode("utf-8")).hexdigest()


def prompt_id() -> str:
    return f"scene/{VERSION}@{prompt_hash()[:12]}"


# ---------------------------------------------------------------- inputs

def labels() -> dict[str, Any]:
    return yaml.safe_load(LABELS.read_text(encoding="utf-8"))["images"]


def board_boxes(dev_run: Path = DEV_RUN) -> dict[str, list[list[float]]]:
    """Per dev image, the sent-image boxes of the boards the frozen dev run's scene listed."""
    out: dict[str, list] = {}
    for line in dev_run.read_text(encoding="utf-8").splitlines()[1:]:
        r = json.loads(line)
        if r["image_id"] in out:
            continue
        boxes = []
        for s in (r.get("scene") or {}).get("signs", []):
            b = (s.get("position") or {}).get("box")
            board = s["code"].startswith(BOARD_CODES) or (s["code"] == "UNKNOWN" and s.get("shape") in ("rectangle", "square"))
            if b and board:
                boxes.append(b)
        out[r["image_id"]] = boxes
    return out


def crop_blocks(image_bytes: bytes, boxes: list[list[float]]) -> list[dict]:
    from PIL import Image

    from vqa.perception.fallback import original_image
    from vqa.perception.image import prepare

    img, im = prepare(image_bytes), original_image(image_bytes)
    c = config()["crop"]
    w, h = img.original_size
    out = []
    for b in boxes:
        x0, y0, x1, y1 = img.to_original(b)
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, max(x1, x0 + 1)), min(h, max(y1, y0 + 1))
        box = tp.pad_box((x0, y0, x1, y1), w, h, c["pad"], c["min_side"])
        part = im.crop(box)
        s = tp.crop_scale(part.size[0], part.size[1], c["short_side"], c["long_edge"])
        part = part.resize((max(1, round(part.size[0] * s)), max(1, round(part.size[1] * s))), Image.LANCZOS)
        buf = io.BytesIO()
        part.save(buf, format="JPEG", quality=c["jpeg_quality"])
        out.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                "data": base64.b64encode(buf.getvalue()).decode("ascii")}})
    return out


def user_content(image_bytes: bytes, variant: str, boxes: list[list[float]]) -> list[dict]:
    from vqa.perception.image import prepare

    content = [prepare(image_bytes).content_block()]
    if variant == "B" and boxes:
        content.append({"type": "text", "text": "Enlarged crops of boards in the photo:"})
        content += crop_blocks(image_bytes, boxes)
    content.append({"type": "text", "text": config()["user_text"]})
    return content


# ---------------------------------------------------------------- the run

def _call(client, user: list) -> tuple[dict | None, list[dict], float]:
    cfg, system = config(), system_prompt()
    replies, cost = [], 0.0
    effort = cfg["effort"][client.model]

    def call(extra=None):
        return client.json_reply(system=system, user=user, max_tokens=cfg["max_tokens"], effort=effort,
                                 purpose="guide trial" + (" retry" if extra else ""), extra_messages=extra)
    try:
        res = call()
        cost += res.cost_usd
        replies.append({"raw_text": res.raw_text, "cost_usd": res.cost_usd})
        if isinstance(res.data.get("boards"), list):
            return res.data, replies, cost
        errors = ["the reply must be a JSON object with a `boards` list"]
    except (LLMRefusal, LLMTruncated) as e:
        replies.append({"raw_text": getattr(e, "raw_text", ""), "error": str(e)})
        return None, replies, cost + getattr(e, "cost_usd", 0.0)
    except LLMBadJSON as e:
        cost += getattr(e, "cost_usd", 0.0)
        replies.append({"raw_text": getattr(e, "raw_text", ""), "error": str(e)})
        errors = [str(e)]
    try:
        res = call(retry_messages(errors))
    except (LLMRefusal, LLMTruncated, LLMBadJSON) as e:
        replies.append({"raw_text": getattr(e, "raw_text", ""), "error": str(e), "retry": True})
        return None, replies, cost + getattr(e, "cost_usd", 0.0)
    cost += res.cost_usd
    replies.append({"raw_text": res.raw_text, "cost_usd": res.cost_usd, "retry": True})
    return (res.data if isinstance(res.data.get("boards"), list) else None), replies, cost


def run(max_spend: float, sdk=None, out_dir: Path = RUNS, variants=("A", "B"), image_path=None) -> Path:
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard

    if prompt_hash() != PINNED:
        raise SystemExit(f"the guide trial prompt differs from its pin: live {prompt_hash()}, pinned {PINNED}")
    image_path = image_path or (lambda i: gs.image_path(i, "train"))
    run_id = uuid.uuid4().hex[:12]
    client = LLMClient(model=MODEL, guard=SpendGuard(max_spend), sdk=sdk, run_id=run_id)
    boxes = board_boxes()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"dev_guide_trial_{run_id}.jsonl"
    ids = list(labels())
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": run_id, "kind": "guide_trial", "model": MODEL, "prompt_id": prompt_id(),
                            "prompt_sha256": prompt_hash(), "variants": list(variants), "images": len(ids),
                            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}) + "\n")
        for n, image_id in enumerate(ids, 1):
            data = Path(image_path(image_id)).read_bytes()
            for v in variants:
                parsed, replies, cost = _call(client, user_content(data, v, boxes.get(image_id, [])))
                f.write(json.dumps({"image_id": image_id, "variant": v, "crops": len(boxes.get(image_id, [])) if v == "B" else 0,
                                    "boards": (parsed or {}).get("boards"), "ok": parsed is not None,
                                    "cost_usd": cost, "replies": replies}, ensure_ascii=False) + "\n")
                f.flush()
            print(f"[{n}/{len(ids)}] {image_id}  spent ${client.guard.spent:.4f}")
    print(f"guide trial {run_id} -> {out}  (spent ${client.guard.spent:.4f})")
    return out


# ---------------------------------------------------------------- scoring (no call)

def fold(text: str | None) -> str:
    t = unicodedata.normalize("NFD", str(text or "")).replace("Đ", "D").replace("đ", "d")
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^A-Z0-9]+", " ", t.upper()).strip()


def metres(d: str | None) -> float | None:
    if not d:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(km|m)\b", str(d), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v * 1000 if m.group(2).lower() == "km" else v


LENIENT = {"slight_left": "left", "slight_right": "right"}


def _entries(boards: list[dict] | None) -> list[dict]:
    return [e for b in (boards or []) for e in (b.get("entries") or []) if isinstance(e, dict) and e.get("text")]


def _speeds(boards: list[dict] | None) -> set[tuple]:
    return {(s.get("kind"), float(s.get("value"))) for b in (boards or []) for s in (b.get("speeds") or [])
            if isinstance(s, dict) and isinstance(s.get("value"), (int, float))}


def score_image(label: dict, boards: list[dict] | None) -> Counter:
    c: Counter = Counter()
    gold, pred = _entries(label.get("boards")), _entries(boards)
    c["label_entries"] += len(gold)
    c["read_entries"] += len(pred)
    used: set[int] = set()
    for g in gold:
        best, bj = 0.0, None
        for j, p in enumerate(pred):
            if j in used:
                continue
            r = difflib.SequenceMatcher(None, fold(g["text"]), fold(p["text"])).ratio()
            if r > best:
                best, bj = r, j
        if bj is None or best < MATCH:
            continue
        used.add(bj)
        p = pred[bj]
        c["matched"] += 1
        if g.get("distance"):
            c["distance_pairs"] += 1
            c["distance_ok"] += metres(g["distance"]) is not None and metres(g["distance"]) == metres(p.get("distance"))
        if g.get("direction"):
            c["direction_pairs"] += 1
            pd = p.get("direction") or "none"
            c["direction_ok"] += pd == g["direction"]
            c["direction_ok_lenient"] += LENIENT.get(pd, pd) == LENIENT.get(g["direction"], g["direction"])
    gs_, ps = _speeds(label.get("boards")), _speeds(boards)
    c["label_speeds"] += len(gs_)
    c["speeds_found"] += len(gs_ & ps)
    c["speeds_read"] += len(ps)
    if not label.get("boards"):
        c["no_text_images"] += 1
        c["no_text_boards_read"] += len(_entries(boards))
    return c


def score(run_file: Path) -> dict[str, Any]:
    lab = labels()
    rows = [json.loads(l) for l in Path(run_file).read_text(encoding="utf-8").splitlines()]
    head, rows = rows[0], rows[1:]
    out: dict[str, Any] = {"run_id": head["run_id"], "prompt_id": head["prompt_id"], "variants": {}}
    for v in head["variants"]:
        c: Counter = Counter()
        cost, failed = 0.0, 0
        for r in (x for x in rows if x["variant"] == v):
            c += score_image(lab[r["image_id"]], r["boards"])
            cost += r["cost_usd"]
            failed += not r["ok"]
        rate = lambda a, b: c[a] / c[b] if c[b] else None  # noqa: E731
        out["variants"][v] = {
            "entry_recall": rate("matched", "label_entries"), "entry_precision": rate("matched", "read_entries"),
            "distance_accuracy": rate("distance_ok", "distance_pairs"),
            "direction_accuracy": rate("direction_ok", "direction_pairs"),
            "direction_accuracy_lenient": rate("direction_ok_lenient", "direction_pairs"),
            "speed_recall": rate("speeds_found", "label_speeds"), "speed_precision": rate("speeds_found", "speeds_read"),
            "entries_read_on_no_text_images": c["no_text_boards_read"], "failed_images": failed,
            "counts": dict(c), "cost_usd": round(cost, 4)}
    return out


# ---------------------------------------------------------------- estimate (no call)

def estimate() -> dict[str, Any]:
    from PIL import Image

    from vqa.perception.image import native_size

    cal = tp.calibration()
    sys_tok = int(len(system_prompt().encode("utf-8")) / 3.0) + 1
    boxes, total, crops = board_boxes(), {"A": 0.0, "B": 0.0}, 0
    for i in labels():
        with Image.open(gs.image_path(i, "train")) as im:
            w, h = im.size
        nw, nh = native_size(w, h)
        img_tok = int(nw * nh / 750) + 1
        n = len(boxes.get(i, []))
        crops += n
        out_tok = round(cal["scene_output_tokens"])            # an upper bound: the scene call's mean
        total["A"] += cost_usd(MODEL, input_tokens=sys_tok + img_tok + 30, output_tokens=out_tok)
        total["B"] += cost_usd(MODEL, input_tokens=sys_tok + img_tok + 30 + n * 450, output_tokens=out_tok)
    return {"images": len(labels()), "board_crops_for_B": crops, "usd_A": round(total["A"], 4),
            "usd_B": round(total["B"], 4), "usd_total": round(total["A"] + total["B"], 4),
            "usd_with_retries_margin": round(1.5 * (total["A"] + total["B"]), 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estimate")
    sub.add_parser("pin")
    r = sub.add_parser("run")
    r.add_argument("--max-spend", type=float, required=True)
    s = sub.add_parser("score")
    s.add_argument("file", type=Path)
    a = ap.parse_args()
    show = lambda x: print(json.dumps(x, indent=2, ensure_ascii=False))  # noqa: E731
    if a.cmd == "estimate":
        show(estimate())
    elif a.cmd == "pin":
        show({"live": prompt_hash(), "pinned": PINNED, "id": prompt_id()})
    elif a.cmd == "run":
        run(a.max_spend)
    else:
        show(score(a.file))


if __name__ == "__main__":
    main()
