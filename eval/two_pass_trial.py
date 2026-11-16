"""Two-pass perception trial: find, then read (owner, 2026-11-16). Eval-only.

A perception-only trial of the original two-pass design, scored against the frozen
Haiku v4 + fallback. No pipeline, parser or answers; nothing in vqa/ changes.

- **Pass 1, find** (`prompts/scene/v5-find-trial/`): one call on the full photo. It
  returns a pixel box per sign and plate, a coarse type from shape and colour
  (`COARSE_TYPES`), the look, rank and side, and the road and vehicles. No codes.
- **Pass 2, read** (`prompts/scene/v5-read-trial/`): every box is cut from the
  original with 20% padding, and all crops of one photo go in one call, each labelled
  with its id and coarse type. The system prompt holds the catalog grouped by coarse
  type (each group is a type's closed candidate list; together they are the full
  catalog), and the existing v4 pictogram set comes first in the user turn. The
  escape: a code from another type's list (`escape: true`), or UNKNOWN. It returns the
  code, the numbers and text, lane rows and condition groups, and for each plate what
  it says and which sign it belongs to.
- The two replies become one v4-format reply (`assemble`), which goes through the
  existing conversion (`vqa.perception.wire.to_scene`, final mode) and verification
  (`vqa.perception.verify.verify`) unchanged. No re-run and no tiles or crops on top.
- Each reply gets one retry that sends only the error, as the scene call. Raw replies
  are kept in the run file, so `rebuild` re-assembles every scene with no call.
- The prompts are pinned by sha256 (`PINNED`); `run` refuses if they differ.

Free analyses (no call), on the frozen runs and gold:

    .venv/bin/python eval/two_pass_trial.py errors       # what today's errors are
    .venv/bin/python eval/two_pass_trial.py coverage     # gold codes outside their type's list
    .venv/bin/python eval/two_pass_trial.py estimate     # cost, calibrated on logged calls

The paid run (Haiku 5.5, medium, one run per set; the owner runs it):

    .venv/bin/python eval/two_pass_trial.py run --set T --max-spend 0.20
    .venv/bin/python eval/two_pass_trial.py run --set public_dev --max-spend 0.25

Afterwards (no call):

    .venv/bin/python eval/two_pass_trial.py report <T trial file> <public_dev trial file>
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import statistics
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval import gold_signs as gs  # noqa: E402
from eval import perception_eval as pe  # noqa: E402
from vqa.kb import Catalog, load_catalog  # noqa: E402
from vqa.llm.client import LLMBadJSON, LLMRefusal, LLMTruncated, parse_json_reply  # noqa: E402
from vqa.llm.pricing import cost_usd  # noqa: E402
from vqa.perception import prompt as scene_prompt  # noqa: E402
from vqa.perception.matching import match, row_of  # noqa: E402
from vqa.perception.wire import retry_messages, to_scene  # noqa: E402

PROMPTS = ROOT / "prompts" / "scene"
FIND, READ = "v5-find-trial", "v5-read-trial"
MODEL = "claude-haiku-5-5"
RUNS = pe.RUNS
SETS = ("T", "public_dev")
# sha256 of each trial prompt (prompt_hash), pinned before the paid run.
PINNED = {
    FIND: "61b2089130a38b5bbe09239ff7fcba0373867d3423bb36ce13ded9ce8175331f",
    READ: "04e209a5fb40345297262a9f64cbfb335d0ba4252a48c90d65ae03f88db44ece",
}
# The frozen Haiku v4 + fallback (crop_always) runs to compare with.
FROZEN = {
    "T": ["T_claude-haiku-5-5_v4+fb_d1ff09db5bf4.jsonl"],            # over pass 1 4e6780670d2f
    "public_dev": ["public_dev_claude-haiku-5-5_v4+fb_b83d5dae690e.jsonl",   # checkpoint 2
                   "public_dev_claude-haiku-5-5_v4+fb_023c1a474288.jsonl",
                   "public_dev_claude-haiku-5-5_v4+fb_9981d8112688.jsonl"],
}
FROZEN_USD_PER_IMAGE = 0.0028          # Haiku pass 1 + re-run + fallback, all-in (DESIGN section 3)
HAIKU_F1_RUN_SPREAD = 2.9              # points of code F1 between Haiku runs (phase 3)

# ---------------------------------------------------------------- coarse types and candidate lists

COARSE_TYPES = ("red_circle", "blue_circle", "yellow_triangle", "red_rect", "blue_rect", "green_rect",
                "white_rect", "plate", "other")


def coarse_of(shape: str | None, border: str | None, background: str | None) -> str:
    """The coarse type of a look (never `plate`: a plate is a role, not a look)."""
    if shape == "circle":
        if border == "red" or background == "red":
            return "red_circle"
        if background == "blue":
            return "blue_circle"
        return "other"
    if shape == "triangle":
        return "yellow_triangle"
    if shape in ("rectangle", "square"):
        if background == "red" or border == "red":
            return "red_rect"
        if background == "blue":
            return "blue_rect"
        if background == "green":
            return "green_rect"
        return "white_rect"
    return "other"


def row_type(row) -> str:
    """A catalog row's coarse type: auxiliary rows are plates, the rest by the catalog's look."""
    if row.category == "auxiliary":
        return "plate"
    v = row.visual
    return coarse_of(v.shape, v.border, v.background)


def candidates(catalog: Catalog | None = None) -> dict[str, list[str]]:
    """Each coarse type's closed candidate list (catalog row codes, in catalog order)."""
    catalog = catalog or load_catalog()
    out: dict[str, list[str]] = {t: [] for t in COARSE_TYPES}
    for s in catalog.signs:
        out[row_type(s)].append(s.code)
    return out


def in_list(code: str | None, ctype: str, catalog: Catalog, cands: dict[str, list[str]] | None = None) -> bool:
    """Whether a code's catalog row is on `ctype`'s candidate list."""
    r = row_of(code, catalog)
    return r is not None and r in (cands or candidates(catalog))[ctype]


def candidate_listing(catalog: Catalog | None = None) -> str:
    catalog = catalog or load_catalog()
    parts = []
    for t, codes in candidates(catalog).items():
        lines = []
        for c in codes:
            s = catalog.get(c)
            v = s.visual
            lines.append(f"{s.code} | {s.name_vi} | {v.shape} / {v.border} / {v.background}"
                         + (" | value" if scene_prompt.carries_value(s) else ""))
        parts.append(f"## {t}\n\n" + ("\n".join(lines) if lines else "(no rows: use the escape)"))
    return "\n\n".join(parts)


# ---------------------------------------------------------------- the trial prompts


def _dir(version: str) -> Path:
    if version not in (FIND, READ):
        raise ValueError(f"not a trial prompt: {version}")
    return PROMPTS / version


def config(version: str) -> dict[str, Any]:
    import yaml
    return yaml.safe_load((_dir(version) / "config.yaml").read_text(encoding="utf-8"))


def _examples(version: str) -> str:
    rows = [json.loads(l) for l in (_dir(version) / "examples.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    return "\n\n".join(f"Example ({r['note']}):\n" + json.dumps(r["output"], ensure_ascii=False,
                                                                 separators=(",", ":")) for r in rows)


def system_prompt(version: str) -> str:
    spec = (_dir(version) / "spec.md").read_text(encoding="utf-8").strip()
    middle = f"\n\n{candidate_listing()}" if version == READ else ""
    return f"{spec}{middle}\n\n# Examples\n\n{_examples(version)}\n"


def prompt_hash(version: str) -> str:
    """sha256 of the system prompt, the config and (read) the v4 pictogram manifest,
    whose sha256 values pin the figure copies."""
    text = system_prompt(version) + "\n--config--\n" + (_dir(version) / "config.yaml").read_text(encoding="utf-8")
    if version == READ:
        src = config(READ)["pictograms_from"]
        text += "\n--pictograms--\n" + (PROMPTS / src / "pictograms.yaml").read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_id(version: str) -> str:
    return f"scene/{version}@{prompt_hash(version)[:12]}"


def check_pins() -> list[str]:
    return [f"{v}: live {prompt_hash(v)} != pinned {PINNED[v]}" for v in (FIND, READ)
            if prompt_hash(v) != PINNED[v]]


# ---------------------------------------------------------------- pass 1: find

Box = tuple[int, int, int, int]


@dataclass
class Found:
    oid: str                         # c1, c2, ... in reply order
    type: str
    box: tuple[float, float, float, float]   # on the sent image
    look: dict[str, Any] = field(default_factory=dict)   # shape, border, background, rank, side, lane


LOOK_FIELDS = ("shape", "border", "background", "rank", "side", "lane")


def parse_find(data: Any, size: tuple[int, int]) -> tuple[list[Found], dict, list, list[str]]:
    """(objects, road, vehicles, errors). An object needs a known type and a box with
    x1 > x0 and y1 > y0; boxes are clipped to the sent image. Errors are for the retry."""
    if not isinstance(data, dict):
        return [], {}, [], ["the reply must be a JSON object"]
    objs = data.get("objects")
    if not isinstance(objs, list):
        return [], {}, [], ["`objects` must be a list"]
    w, h = size
    out, errors = [], []
    for k, o in enumerate(objs, 1):
        where = f"object {k}"
        if not isinstance(o, dict):
            errors.append(f"{where}: must be an object")
            continue
        t = o.get("type")
        if t not in COARSE_TYPES:
            errors.append(f"{where}: type must be one of {', '.join(COARSE_TYPES)}")
            continue
        b = o.get("box")
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                           for v in b)):
            errors.append(f"{where}: box must be [x0, y0, x1, y1] in pixels")
            continue
        x0, y0, x1, y1 = max(0, b[0]), max(0, b[1]), min(w, b[2]), min(h, b[3])
        if not (x1 > x0 and y1 > y0):
            errors.append(f"{where}: box must have x1 > x0 and y1 > y0 inside the image")
            continue
        out.append(Found(f"c{len(out) + 1}", t, (x0, y0, x1, y1),
                         {f: o[f] for f in LOOK_FIELDS if o.get(f) is not None}))
    road = data.get("road") if isinstance(data.get("road"), dict) else {}
    vehicles = data.get("vehicles") if isinstance(data.get("vehicles"), list) else []
    return out, road, vehicles, errors


# ---------------------------------------------------------------- crop geometry


def pad_box(box: Box, w: int, h: int, pad: float = 0.20, min_side: int = 48) -> Box:
    """A box on the original, padded by `pad` of its width / height on each side, grown to
    at least `min_side` around its centre (shifted to stay inside), clipped to the image."""
    import math

    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)

    def span(a: float, b: float, extra: float, n: int) -> tuple[float, float]:
        a, b = max(0.0, a - extra), min(float(n), b + extra)
        need = min(min_side, n) - (b - a)
        if need > 0:
            a, b = a - need / 2, b + need / 2
            if a < 0:
                a, b = 0.0, b - a
            if b > n:
                a, b = a - (b - n), float(n)
        return max(0.0, a), min(float(n), b)

    cx0, cx1 = span(x0, x1, pad * bw, w)
    cy0, cy1 = span(y0, y1, pad * bh, h)
    return (int(math.floor(cx0)), int(math.floor(cy0)), int(math.ceil(cx1)), int(math.ceil(cy1)))


def crop_scale(w: int, h: int, short_side: int = 256, long_edge: int = 768) -> float:
    """Enlarge to `short_side` on the short side; never past `long_edge` (a big crop shrinks)."""
    s = max(1.0, short_side / min(w, h))
    return min(s, long_edge / max(w, h))


def crop_boxes(found: list[Found], img) -> dict[str, Box]:
    """Each object's padded crop box on the original image."""
    c = config(READ)["crop"]
    w, h = img.original_size
    out = {}
    for f in found:
        x0, y0, x1, y1 = img.to_original(f.box)
        b = (max(0, x0), max(0, y0), min(w, x1), min(h, y1))
        if b[2] <= b[0] or b[3] <= b[1]:
            b = (max(0, min(x0, w - 1)), max(0, min(y0, h - 1)), max(1, min(x1, w)), max(1, min(y1, h)))
        out[f.oid] = pad_box(b, w, h, c["pad"], c["min_side"])
    return out


def crop_block(im, box: Box) -> dict[str, Any]:
    import base64

    from PIL import Image

    c = config(READ)["crop"]
    part = im.crop(box)
    w, h = part.size
    s = crop_scale(w, h, c["short_side"], c["long_edge"])
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    if (nw, nh) != (w, h):
        part = part.resize((nw, nh), Image.LANCZOS)
    buf = io.BytesIO()
    part.save(buf, format="JPEG", quality=c["jpeg_quality"])
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode("ascii")}}


# ---------------------------------------------------------------- pass 2: read


def read_user_content(found: list[Found], blocks: dict[str, dict]) -> list[dict[str, Any]]:
    """The existing pictogram set (cached prefix), then each crop's label and image, then
    the instruction."""
    out = [*scene_prompt.pictogram_blocks(config(READ)["pictograms_from"])]
    if out and out[-1].get("type") == "text" and out[-1]["text"] == "The photo:":
        out[-1] = {"type": "text", "text": "The crops:"}
    for f in found:
        out.append({"type": "text", "text": f"Crop {f.oid} ({f.type})"})
        out.append(blocks[f.oid])
    out.append({"type": "text", "text": config(READ)["user_text"]})
    return out


READ_SIGN_FIELDS = ("code", "confidence", "value", "unit", "alt", "lanes", "rules")


def parse_read(data: Any, ids: list[str]) -> tuple[dict[str, dict], list[str]]:
    """({crop id: entry}, errors). Every crop id must have an entry; codes and fields are
    checked later by the wire conversion (final mode)."""
    if not isinstance(data, dict) or not isinstance(data.get("crops"), list):
        return {}, ["the reply must be a JSON object with a `crops` list"]
    out = {}
    for e in data["crops"]:
        if isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"] in ids and e["id"] not in out:
            out[e["id"]] = e
    missing = [i for i in ids if i not in out]
    return out, ([f"no entry for crops {', '.join(missing)}; every crop needs one"] if missing else [])


# ---------------------------------------------------------------- plates and assembly


def plate_owner_by_geometry(plate: Found, signs: list[Found]) -> str | None:
    """The sign directly above the plate (overlapping it across, nearest bottom edge above
    the plate's centre); else the sign whose centre is nearest."""
    px0, py0, px1, py1 = plate.box
    pcx, pcy = (px0 + px1) / 2, (py0 + py1) / 2
    above = [s for s in signs if min(px1, s.box[2]) - max(px0, s.box[0]) > 0 and (s.box[1] + s.box[3]) / 2 < pcy]
    if above:
        return min(above, key=lambda s: abs(py0 - s.box[3])).oid
    if not signs:
        return None
    return min(signs, key=lambda s: ((s.box[0] + s.box[2]) / 2 - pcx) ** 2 + ((s.box[1] + s.box[3]) / 2 - pcy) ** 2).oid


def assign_plates(found: list[Found], readings: dict[str, dict]) -> tuple[dict[str, str], Counter]:
    """{plate id: sign id}: the read pass's `belongs_to` when it names a sign crop, else geometry."""
    signs = [f for f in found if f.type != "plate"]
    sign_ids = {s.oid for s in signs}
    out, how = {}, Counter()
    for p in (f for f in found if f.type == "plate"):
        b = (readings.get(p.oid) or {}).get("belongs_to")
        if b in sign_ids:
            out[p.oid] = b
            how["model"] += 1
        elif (g := plate_owner_by_geometry(p, signs)) is not None:
            out[p.oid] = g
            how["geometry"] += 1
        else:
            how["no_sign"] += 1
    return out, how


PLATE_FIELDS = ("kind", "code", "text", "time_windows", "days", "vehicles", "actions", "rules", "lanes", "distance_m")


def _plate(entry: dict) -> dict:
    p = entry.get("plate") if isinstance(entry.get("plate"), dict) else entry
    out = {k: p[k] for k in PLATE_FIELDS if p.get(k) is not None}
    out.setdefault("kind", "text")
    return out


def assemble(found: list[Found], readings: dict[str, dict], road: dict, vehicles: list,
             catalog: Catalog | None = None) -> tuple[dict, dict[str, Any]]:
    """The two replies as one v4-format reply, and the trial's counts."""
    catalog = catalog or load_catalog()
    cands = candidates(catalog)
    owner, how = assign_plates(found, readings)
    signs, stats = [], Counter()
    by_id: dict[str, dict] = {}
    for f in found:
        if f.type == "plate":
            continue
        e = readings.get(f.oid)
        s = {k: f.look[k] for k in LOOK_FIELDS if k in f.look}
        s["box"] = [round(v) for v in f.box]
        if e is None:
            s.update(code="UNKNOWN", confidence="low")
            stats["unread"] += 1
        else:
            s.update({k: e[k] for k in READ_SIGN_FIELDS if e.get(k) is not None})
            s.setdefault("code", "UNKNOWN")
            code = s["code"]
            if code == "UNKNOWN":
                stats["unknown"] += 1
            elif row_of(code, catalog) is not None and not in_list(code, f.type, catalog, cands):
                stats["escape"] += 1                 # counted from the code, not the model's flag
            if e.get("escape"):
                stats["escape_flagged"] += 1
        s["plates"] = []
        signs.append(s)
        by_id[f.oid] = s
    for f in found:
        if f.type == "plate" and f.oid in owner:
            by_id[owner[f.oid]]["plates"].append(_plate(readings.get(f.oid) or {}))
    stats.update({"objects": len(found), "signs": len(signs), "plates": sum(f.type == "plate" for f in found),
                  "plates_by_model": how["model"], "plates_by_geometry": how["geometry"],
                  "plates_without_sign": how["no_sign"]})
    return {"signs": signs, "road": road, "vehicles": vehicles}, dict(stats)


# ---------------------------------------------------------------- one image


def _reply(pass_: str, text: str, res=None, error: str | None = None) -> dict[str, Any]:
    return {"pass": pass_, "raw_text": text, "cost_usd": getattr(res, "cost_usd", 0.0),
            "usage": getattr(res, "usage", None), "request_id": getattr(res, "request_id", None),
            **({"error": error} if error else {})}


def _call(client, version: str, user: list, pass_: str, check, replies: list) -> tuple[Any, float, str | None]:
    """One call plus one retry that sends only the error. Returns (parsed result of
    `check`, cost, error). `check(data, final)` returns (value, errors)."""
    system, cfg = system_prompt(version), config(version)
    effort = cfg["effort"][client.model]
    cost = 0.0

    def call(extra=None):
        return client.json_reply(system=system, user=user, max_tokens=cfg["max_tokens"], effort=effort,
                                 purpose=f"trial {pass_}" + (" retry" if extra else ""), extra_messages=extra)

    errors: list[str]
    try:
        res = call()
    except (LLMRefusal, LLMTruncated) as e:
        replies.append(_reply(pass_, getattr(e, "raw_text", "") or "", error=f"{type(e).__name__}: {e}"))
        return None, getattr(e, "cost_usd", 0.0), f"{pass_}: {type(e).__name__}"
    except LLMBadJSON as e:
        cost += getattr(e, "cost_usd", 0.0)
        replies.append(_reply(pass_, getattr(e, "raw_text", "") or "", error=str(e)))
        errors = [str(e)]
    else:
        cost += res.cost_usd
        replies.append(_reply(pass_, res.raw_text, res))
        value, errors = check(res.data, False)
        if not errors:
            return value, cost, None
    try:
        res = call(retry_messages(errors))
    except (LLMRefusal, LLMTruncated, LLMBadJSON) as e:
        cost += getattr(e, "cost_usd", 0.0)
        replies.append(_reply(f"{pass_} retry", getattr(e, "raw_text", "") or "", error=str(e)))
        return None, cost, f"{pass_}: after the retry: {type(e).__name__}"
    cost += res.cost_usd
    replies.append(_reply(f"{pass_} retry", res.raw_text, res))
    value, _ = check(res.data, True)
    return value, cost, None


def build_scene(replies: list[dict], scene_id: str, size: tuple[int, int], catalog: Catalog | None = None):
    """The scene from stored raw replies (no call, no image): the last usable find reply,
    the last usable read reply, assembly, the wire conversion and verification."""
    from vqa.perception.verify import verify

    catalog = catalog or load_catalog()

    def last(prefix: str):
        for r in reversed(replies):
            if r["pass"].startswith(prefix) and not r.get("error"):
                try:
                    return parse_json_reply(r["raw_text"])
                except LLMBadJSON:
                    continue
        return None

    fdata = last("find")
    if fdata is None:
        return None, ["no usable find reply"], {}, {}
    found, road, vehicles, _ = parse_find(fdata, size)
    rdata = last("read") if found else {"crops": []}
    readings, _ = parse_read(rdata, [f.oid for f in found]) if rdata is not None else ({}, [])
    issues = [] if rdata is not None else ["no usable read reply: every sign is UNKNOWN"]
    wire, stats = assemble(found, readings, road, vehicles, catalog)
    w = to_scene(wire, scene_id, final=True, catalog=catalog)
    scene, more = verify(w.scene, catalog)
    stats["dropped"] = len(w.dropped)
    return scene, issues + [f"dropped: {d}" for d in w.dropped] + more, w.raw_codes, stats


def perceive_trial(image_bytes: bytes, client, catalog: Catalog | None = None) -> dict[str, Any]:
    """Find, read, assemble, verify. Returns the run-file row (without the image id)."""
    from vqa.perception.fallback import original_image
    from vqa.perception.image import prepare

    img = prepare(image_bytes)
    replies: list[dict] = []
    cost, error = 0.0, None
    user = [img.content_block(), {"type": "text", "text": config(FIND)["user_text"]}]
    find = lambda d, final: (lambda r: (r, r[3]))(parse_find(d, img.size))  # noqa: E731
    parsed, c, error = _call(client, FIND, user, "find", find, replies)
    cost += c
    crops = {}
    if parsed is not None and parsed[0]:
        found = parsed[0]
        im = original_image(image_bytes)
        crops = crop_boxes(found, img)
        blocks = {oid: crop_block(im, b) for oid, b in crops.items()}
        ids = [f.oid for f in found]
        _, c, error = _call(client, READ, read_user_content(found, blocks), "read",
                            lambda d, final: parse_read(d, ids), replies)
        cost += c
    scene, issues, raw_codes, stats = build_scene(replies, img.sha256[:12], img.size, catalog)
    return {"ok": scene is not None and error is None, "error": error, "cost_usd": cost, "issues": issues,
            "raw_codes": raw_codes, "scene": scene.model_dump(mode="json", by_alias=True) if scene else None,
            "sent_size": list(img.size), "scale": img.scale, "crop_boxes": {k: list(v) for k, v in crops.items()},
            "trial_stats": stats, "replies": replies,
            "calls": sum(not r["pass"].endswith("retry") for r in replies),
            "retries": sum(r["pass"].endswith("retry") for r in replies)}


# ---------------------------------------------------------------- the run


def header(set_name: str, run_id: str) -> dict[str, Any]:
    return {"run_id": run_id, "set": set_name, "model": MODEL,
            "prompt_id": f"{prompt_id(FIND)}+{prompt_id(READ)}", "gate": pe.GATE["name"],
            "trial": {"name": "two_pass_find_read", "find": prompt_id(FIND), "read": prompt_id(READ),
                      "find_sha256": prompt_hash(FIND), "read_sha256": prompt_hash(READ),
                      "pictograms_from": config(READ)["pictograms_from"], "effort": config(FIND)["effort"][MODEL],
                      "use_cache": False},
            "label": "tuned" if set_name == "public_dev" else "development",
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


def run(set_name: str, max_spend: float, sdk=None, out_dir: Path = RUNS, images=None, image_path=None) -> Path:
    from vqa.llm.client import LLMClient
    from vqa.llm.spend import SpendGuard

    if set_name not in SETS:
        raise SystemExit(f"--set must be one of {SETS}")
    if bad := check_pins():
        raise SystemExit("the trial prompts differ from their pins:\n  " + "\n  ".join(bad))
    images = images if images is not None else pe.set_images(set_name)
    image_path = image_path or gs.image_path
    run_id = uuid.uuid4().hex[:12]
    client = LLMClient(model=MODEL, guard=SpendGuard(max_spend), sdk=sdk, run_id=run_id)
    catalog = load_catalog()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{set_name}_{MODEL}_v5trial_{run_id}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(header(set_name, run_id)) + "\n")
        for n, (image_id, split) in enumerate(images, 1):
            row = perceive_trial(Path(image_path(image_id, split)).read_bytes(), client, catalog)
            f.write(json.dumps({"image_id": image_id, **row}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{n}/{len(images)}] {image_id}: {'ok' if row['ok'] else row['error']}  "
                  f"spent ${client.guard.spent:.4f}")
    print(f"trial run {run_id} -> {out}  (spent ${client.guard.spent:.4f})")
    return out


def rebuild(path: Path, out: Path | None = None) -> Path:
    """Re-assemble every scene of a trial run from its stored replies, with the current
    code. No call and no image."""
    head, rows = pe.load_run(path)
    catalog = load_catalog()
    out = out or Path(path).with_suffix(".rebuilt.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({**head, "rebuilt_from": Path(path).name}) + "\n")
        for r in rows:
            scene, issues, raw_codes, stats = build_scene(r["replies"], (r.get("scene") or {}).get("scene_id")
                                                          or r["image_id"][:12], tuple(r["sent_size"]), catalog)
            f.write(json.dumps({**r, "scene": scene.model_dump(mode="json", by_alias=True) if scene else None,
                                "issues": issues, "raw_codes": raw_codes, "trial_stats": stats},
                               ensure_ascii=False) + "\n")
    return out


# ---------------------------------------------------------------- analysis (no call)


def _plates_key(plates: list[dict] | None) -> tuple:
    """What a plate comparison checks: kinds, and the time windows of each plate."""
    def one(p):
        tw = tuple(sorted((t.get("start"), t.get("end")) for t in (p.get("time_windows") or [])))
        return (p.get("kind"), tw)
    return tuple(sorted(one(p) for p in (plates or [])))


def classify(gold: list[dict], pred: list[dict], catalog: Catalog) -> list[dict | None]:
    """Per gold sign, with the gate's matching (None for excluded gold):
    status: tp | miss | wrong_confident (high/medium, a catalog code) | wrong_unsure (low or UNKNOWN);
    for a tp: value_wrong / plates_wrong when gold has a value / plates."""
    by_gold = dict(match([pe._view(g) for g in gold], [pe._view(p) for p in pred], catalog))
    out: list[dict | None] = []
    for i, g in enumerate(gold):
        if pe.excluded(g):
            out.append(None)
            continue
        if i not in by_gold:
            out.append({"status": "miss"})
            continue
        p = pred[by_gold[i]]
        rp, rg = row_of(p.get("code"), catalog), row_of(g["code"], catalog)
        if rp is not None and rp == rg:
            d: dict[str, Any] = {"status": "tp"}
            if g.get("value") is not None:
                d["value_wrong"] = p.get("value") != g["value"]
            if g.get("plates"):
                d["plates_wrong"] = _plates_key(p.get("plates")) != _plates_key(g.get("plates"))
                d["plates_missing"] = not p.get("plates")
            out.append(d)
        elif p.get("code") in (None, "UNKNOWN") or p.get("confidence") == "low":
            out.append({"status": "wrong_unsure"})
        else:
            out.append({"status": "wrong_confident", "same_type": coarse_of(p.get("shape"), p.get("border"), p.get("background"))
                        == _gold_list_type(g["code"], catalog)})
    return out


def _gold_list_type(code: str, catalog: Catalog) -> str | None:
    r = row_of(code, catalog)
    return row_type(catalog.get(r)) if r else None


def breakdown(path: Path, gold: dict | None = None, catalog: Catalog | None = None) -> dict[str, Any]:
    """Error counts of one run file over readable gold signs, plus false positives."""
    gold = gold if gold is not None else pe.gold_rows()
    catalog = catalog or load_catalog()
    head, rows = pe.load_run(path)
    c: Counter = Counter()
    for r in rows:
        g = gold[r["image_id"]]["signs"]
        pred = (r["scene"] or {}).get("signs", [])
        st = classify(g, pred, catalog)
        for s in st:
            if s is None:
                continue
            c["gold"] += 1
            c[s["status"]] += 1
            if s["status"] == "wrong_confident":
                c["wrong_confident_same_type"] += s["same_type"]
            for k in ("value_wrong", "plates_wrong"):
                if k in s:
                    c[k.replace("_wrong", "_pairs")] += 1
                    c[k] += s[k]
            c["plates_missing"] += s.get("plates_missing", False)
        matched = {j for _, j in match([pe._view(x) for x in g], [pe._view(p) for p in pred], catalog)}
        fps = [pred[j] for j in range(len(pred)) if j not in matched]
        c["false_positive"] += len(fps)
        c["false_positive_unknown"] += sum(p.get("code") in (None, "UNKNOWN") for p in fps)
        c["predicted_unknown"] += sum(p.get("code") in (None, "UNKNOWN") for p in pred)
    return {"run_id": head["run_id"], "set": head["set"], **dict(c)}


def errors_report(sets=SETS) -> dict[str, Any]:
    """Today's frozen Haiku v4 + fallback errors, per set (public_dev: per run and the mean)."""
    gold, catalog = pe.gold_rows(), load_catalog()
    out = {}
    for s in sets:
        runs = [breakdown(RUNS / f, gold, catalog) for f in FROZEN[s]]
        keys = sorted({k for r in runs for k in r if k not in ("run_id", "set")})
        out[s] = {"runs": runs, "mean": {k: statistics.mean(r.get(k, 0) for r in runs) for k in keys}}
    return out


def coverage(sets=SETS) -> dict[str, Any]:
    """From gold only: how often the coarse type of a gold sign's look (as gold records
    it, the best case for the find pass) puts its gold code outside that type's list."""
    gold, catalog = pe.gold_rows(), load_catalog()
    cands = candidates(catalog)
    out: dict[str, Any] = {"list_sizes": {t: len(v) for t, v in cands.items()}}
    for s in sets:
        ids = [i for i, _ in pe.set_images(s)]
        c: Counter = Counter()
        outside: Counter = Counter()
        for i in ids:
            for g in gold[i]["signs"]:
                if pe.excluded(g):
                    continue
                t = coarse_of(g.get("shape"), g.get("border"), g.get("background"))
                c["signs"] += 1
                if row_of(g["code"], catalog) is None:
                    c["gold_code_not_in_catalog"] += 1
                    continue
                if not in_list(g["code"], t, catalog, cands):
                    c["outside"] += 1
                    outside[f"{g['code']} seen as {t} (listed as {_gold_list_type(g['code'], catalog)})"] += 1
                for p in g.get("plates") or []:
                    c["plates"] += 1
                    if p.get("code"):
                        c["plates_with_code"] += 1
                        c["plate_code_outside"] += not in_list(p["code"], "plate", catalog, cands)
        out[s] = {**dict(c), "outside_share": c["outside"] / c["signs"] if c["signs"] else None,
                  "outside_cases": dict(outside.most_common())}
    return out


# ---------------------------------------------------------------- estimate (no call)


def _log_calls() -> list[dict]:
    if not pe.LOG.exists():
        raise SystemExit("no usage log to calibrate from")
    return [json.loads(l) for l in pe.LOG.read_text(encoding="utf-8").splitlines() if l.strip()]


def calibration() -> dict[str, float]:
    """Logged Haiku calls of the frozen runs: the mean scene call's output tokens (pass 1,
    re-run) and the mean crop call's output tokens, and the share of crop and scene
    first calls that needed a retry."""
    calls = [c for c in _log_calls() if c.get("model") == MODEL]
    heads = [pe.load_run(RUNS / f)[0] for s in SETS for f in FROZEN[s]]
    pass1 = {h["fallback"]["pass1_run"] for h in heads}
    fb = {h["run_id"] for h in heads if not h["fallback"].get("replayed_from")}
    scene = [c for c in calls if c.get("run_id") in pass1 and c["purpose"] == "scene"]
    crop = [c for c in calls if c["purpose"] == "scene crop" and (c.get("run_id") in fb or not fb)]
    if not scene or not crop:
        raise SystemExit("no logged frozen scene or crop calls to calibrate from")
    m = lambda xs, k: statistics.mean(x.get(k) or 0 for x in xs)  # noqa: E731
    return {"scene_calls": len(scene), "scene_output_tokens": m(scene, "output_tokens"),
            "scene_input_tokens": m(scene, "input_tokens"),
            "scene_retry_share": sum(c["status"] == "bad_json" for c in scene) / len(scene),
            "crop_calls": len(crop), "crop_output_tokens": m(crop, "output_tokens"),
            "crop_retry_share": sum(c["status"] == "bad_json" for c in crop) / len(crop)}


def estimate(sets=SETS) -> dict[str, Any]:
    """Cost per set with no call. Find: the photo at native size, the find system prompt
    (cached after the first image), output = the logged mean v4 scene output (an upper
    bound: find replies carry no codes). Read: the read system prompt and the v4
    pictograms (cached), one crop per sign and plate of the frozen run's scene on the
    same image (a proxy for what find will list), each crop's tokens from its padded box,
    output = the logged mean crop output per crop. A 2x margin covers retries and
    longer replies."""
    import base64

    from PIL import Image

    from vqa.perception.image import native_size

    cal = calibration()
    bpt = pe.BYTES_PER_TOKEN
    tok = lambda s: int(len(s.encode("utf-8")) / bpt) + 1  # noqa: E731
    find_sys = tok(system_prompt(FIND))
    read_sys = tok(system_prompt(READ))
    pict = 0
    for b in scene_prompt.pictogram_blocks(config(READ)["pictograms_from"]):
        if b["type"] == "text":
            pict += tok(b["text"])
        else:
            with Image.open(io.BytesIO(base64.b64decode(b["source"]["data"]))) as im:
                pict += int(im.size[0] * im.size[1] / 750) + 1
    cc = config(READ)["crop"]
    out: dict[str, Any] = {"calibration": {k: round(v, 3) for k, v in cal.items()},
                           "find_system_tokens": find_sys, "read_prefix_tokens": read_sys + pict}
    total = 0.0
    for s in sets:
        _, rows = pe.load_run(RUNS / FROZEN[s][0])
        split_of = dict(pe.set_images(s))
        usd, objects = 0.0, 0
        for k, r in enumerate(rows):
            with Image.open(gs.image_path(r["image_id"], split_of[r["image_id"]])) as im:
                w, h = im.size
            nw, nh = native_size(w, h)
            scale = nw / w
            first = k == 0
            # the find system prompt may be below the minimum cacheable length: priced uncached
            usd += cost_usd(MODEL, input_tokens=find_sys + int(nw * nh / 750) + 40,
                            output_tokens=round(cal["scene_output_tokens"]))
            signs = (r["scene"] or {}).get("signs", [])
            n = len(signs) + sum(len(x.get("plates") or []) for x in signs)
            objects += n
            if not n:
                continue
            crop_tokens = 0
            for x in signs:
                b = (x.get("position") or {}).get("box") or [0, 0, 60 * scale, 60 * scale]
                ob = tuple(round(v / scale) for v in b)
                pb = pad_box((max(0, ob[0]), max(0, ob[1]), min(w, max(ob[2], ob[0] + 1)), min(h, max(ob[3], ob[1] + 1))),
                             w, h, cc["pad"], cc["min_side"])
                cw, ch = pb[2] - pb[0], pb[3] - pb[1]
                sc = crop_scale(cw, ch, cc["short_side"], cc["long_edge"])
                crop_tokens += int(cw * sc * ch * sc / 750) + 1 + 10
            crop_tokens += sum(len(x.get("plates") or []) for x in signs) * 120     # a plate crop, about 256 x 350
            usd += cost_usd(MODEL, input_tokens=crop_tokens + 30, output_tokens=round(n * cal["crop_output_tokens"]),
                            **({"cache_write_tokens": read_sys + pict} if first else {"cache_read_tokens": read_sys + pict}))
        out[s] = {"images": len(rows), "objects_proxy": objects, "usd": round(usd, 4), "usd_with_margin": round(2 * usd, 4),
                  "usd_per_image": round(usd / len(rows), 5), "frozen_usd_per_image": FROZEN_USD_PER_IMAGE}
        total += usd
    out["total_usd"], out["total_usd_with_margin"] = round(total, 4), round(2 * total, 4)
    return out


# ---------------------------------------------------------------- the report after the run (no call)


def _pick(m: dict, mean: bool) -> dict[str, Any]:
    p = "mean_" if mean else ""
    keys = ("sign_recall", "sign_code_f1", "sign_code_f1_strict", "sign_code_f1_rule_bearing", "value_accuracy")
    out = {k: m.get(p + k) for k in keys}
    out["sign_recall_ci95"], out["sign_code_f1_ci95"] = m.get("sign_recall_ci95"), m.get("sign_code_f1_ci95")
    out["images"], out["gold_signs"] = m.get("images"), m.get("gold_signs")
    return out


def against_frozen(trial: Path, frozen: list[Path], gold: dict, catalog: Catalog) -> dict[str, Any]:
    """Per gold sign on the same image: codes fixed and broken, number and plate fixes and
    breaks, misses added and removed, the trial against each frozen run (and the mean)."""
    _, trows = pe.load_run(trial)
    tscene = {r["image_id"]: (r["scene"] or {}).get("signs", []) for r in trows}
    per = []
    for fp in frozen:
        _, frows = pe.load_run(fp)
        c: Counter = Counter()
        for r in frows:
            i = r["image_id"]
            if i not in tscene:
                continue
            g = gold[i]["signs"]
            a = classify(g, (r["scene"] or {}).get("signs", []), catalog)
            b = classify(g, tscene[i], catalog)
            for x, y in zip(a, b):
                if x is None:
                    continue
                if x["status"] != "tp" and y["status"] == "tp":
                    c["codes_fixed"] += 1
                if x["status"] == "tp" and y["status"] != "tp":
                    c["codes_broken"] += 1
                if x["status"] != "miss" and y["status"] == "miss":
                    c["misses_added"] += 1
                if x["status"] == "miss" and y["status"] != "miss":
                    c["misses_removed"] += 1
                for k in ("value_wrong", "plates_wrong"):
                    if k in x and k in y:            # both read the code right
                        name = {"value_wrong": "values", "plates_wrong": "plates"}[k]
                        c[f"{name}_fixed"] += x[k] and not y[k]
                        c[f"{name}_broken"] += y[k] and not x[k]
        per.append({"frozen_run": pe.load_run(fp)[0]["run_id"], **dict(c)})
    keys = sorted({k for p in per for k in p if k != "frozen_run"})
    return {"per_frozen_run": per, "mean": {k: statistics.mean(p.get(k, 0) for p in per) for k in keys}}


def report(trials: list[Path]) -> dict[str, Any]:
    gold, catalog = pe.gold_rows(), load_catalog()
    out: dict[str, Any] = {"caveat": (f"One trial run per set. Haiku's code F1 varies about {HAIKU_F1_RUN_SPREAD} points "
                                      "between runs, so a gap smaller than that is not evidence. public_dev is tuned.")}
    for t in trials:
        head, rows = pe.load_run(t)
        s = head["set"]
        frozen = [RUNS / f for f in FROZEN[s]]
        trep = pe.score([t])["summaries"][0]
        frep = pe.score(frozen)["summaries"][0]
        stats = Counter()
        for r in rows:
            stats.update({k: v for k, v in (r.get("trial_stats") or {}).items() if isinstance(v, (int, float))})
        cost = sum(r["cost_usd"] for r in rows)
        out[s] = {
            "label": head.get("label"), "trial_run": head["run_id"], "frozen_runs": frep["run_ids"],
            "trial": {"all_images": _pick(trep["all_images"], True),
                      "non_duplicate_images": _pick(trep["non_duplicate_images"], True)},
            "frozen": {"all_images": _pick(frep["all_images"], True),
                       "non_duplicate_images": _pick(frep["non_duplicate_images"], True)},
            "errors": {"trial": breakdown(t, gold, catalog),
                       "frozen_mean": {k: statistics.mean(breakdown(f, gold, catalog).get(k, 0) for f in frozen)
                                       for k in breakdown(frozen[0], gold, catalog) if k not in ("run_id", "set")}},
            "against_frozen": against_frozen(t, frozen, gold, catalog),
            "escape": {"used": stats["escape"], "flagged_by_model": stats["escape_flagged"],
                       "sign_crops": stats["signs"], "unknown": stats["unknown"], "unread": stats["unread"]},
            "plates": {"found": stats["plates"], "by_model": stats["plates_by_model"],
                       "by_geometry": stats["plates_by_geometry"], "without_sign": stats["plates_without_sign"]},
            "failed_images": sum(not r["ok"] for r in rows),
            "retries": sum(r.get("retries", 0) for r in rows),
            "cost_usd": round(cost, 4), "usd_per_image": round(cost / len(rows), 5) if rows else None,
            "frozen_usd_per_image": FROZEN_USD_PER_IMAGE,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("errors")
    sub.add_parser("coverage")
    sub.add_parser("estimate")
    sub.add_parser("pins")
    r = sub.add_parser("run")
    r.add_argument("--set", required=True, choices=SETS)
    r.add_argument("--max-spend", type=float, required=True)
    b = sub.add_parser("rebuild")
    b.add_argument("file", type=Path)
    p = sub.add_parser("report")
    p.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args()
    show = lambda x: print(json.dumps(x, indent=2, ensure_ascii=False, default=str))  # noqa: E731
    if a.cmd == "errors":
        show(errors_report())
    elif a.cmd == "coverage":
        show(coverage())
    elif a.cmd == "estimate":
        show(estimate())
    elif a.cmd == "pins":
        show({v: {"live": prompt_hash(v), "pinned": PINNED[v], "id": prompt_id(v)} for v in (FIND, READ)})
    elif a.cmd == "run":
        run(a.set, a.max_spend)
    elif a.cmd == "rebuild":
        print(rebuild(a.file))
    else:
        show(report(a.files))


if __name__ == "__main__":
    main()
