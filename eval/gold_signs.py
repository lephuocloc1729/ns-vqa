"""Gold sign labels (phase 3, item 1): pick set T, pre-fill drafts with Claude
Opus 5.5, write review sheets, import the reviewed labels.

The rules a labeller follows are in docs/gold_signs_guide.md; the pre-fill reads
that file as its instructions.

    .venv/bin/python eval/gold_signs.py select [--n 36]      # set T -> data/splits/gold_signs_set_t.json
    .venv/bin/python eval/gold_signs.py estimate [--model M] [--remaining] [--count]  # no spend
    .venv/bin/python eval/gold_signs.py prefill --max-spend N [--model M]  # sequential, cached, guarded
    .venv/bin/python eval/gold_signs.py sheet                # one YAML per image + sheet.html
    .venv/bin/python eval/gold_signs.py import [--replace]   # done YAMLs -> gold_signs_v1.jsonl
    .venv/bin/python eval/gold_signs.py import --private     # private labels -> gitignored folder

Sets: public_dev (the gate set) and set T (train images for prompt tuning, in no
duplicate group with any public test image). The
private split is labelled only after the benchmark run (plan D1, C2), from YAML
files under PRIVATE_OUT; its labels are written only there, and only if git
ignores that path. Nothing here reads public_holdout or private question files.

Committed: the set-T id list and gold_signs_v1.jsonl (image ids and labels).
Gitignored: everything under gold_signs_v1/work/ and the whole private folder.
"""

from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import html
import io
import json
import os
import random
import re
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from eval.gold_intents import category  # noqa: E402
from vqa.kb import load_catalog  # noqa: E402
from vqa.llm.client import LLMBadJSON, parse_json_reply  # noqa: E402
from vqa.llm.pricing import cost_usd, worst_case_usd  # noqa: E402
from vqa.llm.spend import SpendGuard, log_call  # noqa: E402
from vqa.schemas import SceneVehicle, Sign, VehicleClass  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(os.environ.get("VQA_DATASET_DIR", ROOT / "VLSP2025-MLQA-Natural")) / "dataset"
TRAIN_IMAGES = DATASET / "train data" / "train_images"
PUBLIC_IMAGES = DATASET / "public_test data" / "public_test_images"
TRAIN_QA = DATASET / "train data" / "vlsp_2025_train.json"
PUBLIC_QA = DATASET / "public_test data" / "vlsp_2025_public_test.json"
SPLIT_FILE = ROOT / "data" / "splits" / "public_split.json"
DUPLICATES = ROOT / "data" / "splits" / "duplicates.json"
SET_T = ROOT / "data" / "splits" / "gold_signs_set_t.json"
GUIDE = ROOT / "docs" / "gold_signs_guide.md"

OUT = ROOT / "data" / "annotations" / "gold_signs_v1"
WORK = OUT / "work"                      # gitignored: drafts, label YAMLs, sheet
GOLD = OUT / "gold_signs_v1.jsonl"       # committed
PRIVATE_OUT = ROOT / "data" / "annotations" / "gold_signs_private"   # gitignored, whole folder
PRIVATE_GOLD = PRIVATE_OUT / "gold_signs_private.jsonl"

MODEL = "claude-opus-5-5"              # default drafter (plan D2)
MODELS = ("claude-opus-5-5", "claude-haiku-5-5")
EFFORT = "medium"
MAX_TOKENS = 8000          # a dense scene's JSON (~1,500 tokens) plus adaptive thinking
# Bump when the pre-fill prompt text changes. p2 is p1's text drafted by Haiku 5.5:
# the version marks the owner's change of drafter (plan D2, 2026-11-15).
PREFILL_VERSIONS = {"claude-opus-5-5": "p1", "claude-haiku-5-5": "p2"}
PREFILL_VERSION = PREFILL_VERSIONS[MODEL]
SEED = 20261115
SET_T_SIZE = 36            # plan: 30-40
MIN_CACHE_SHARE = 0.9
# Bytes per token measured on the parser's v6 prompt (30,987 bytes read as 15,213
# cached tokens, 2026-11-15): Vietnamese text costs ~2 bytes per token.
BYTES_PER_TOKEN = 2.04
EXPECTED_OUTPUT_TOKENS = 1500   # ~700 of JSON for a typical scene, plus thinking
NATIVE_LONG_EDGE = 1568
NATIVE_MAX_PIXELS = 1_150_000

SPLITS = ("train", "public_dev", "private")
STATUSES = ("todo", "done", "skip")
LABEL_KEYS = {"image_id", "split", "status", "violation_question", "signs", "vehicles", "notes"}
# Gold-only sign keys, not in the scene schema. local_notice holds the verbatim text of a
# readable standalone local notice (no QCVN 41 main sign); see docs/gold_signs_guide.md.
SIGN_EXTRA_KEYS = {"readable", "local_notice"}
LOCAL_NOTICE_FORBIDS = ("plates", "rules", "lanes", "value", "unit")
VIOLATION_RE = re.compile(r"vi phạm", re.I)


# --------------------------------------------------------------------------- data

def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dev_images() -> set[str]:
    return set(_json(SPLIT_FILE)["public_dev"]["images"])


def public_images() -> set[str]:
    """Every public test image id, from both halves of public_split.json (image ids
    only; no question file is read)."""
    split = _json(SPLIT_FILE)
    return set().union(*(set(v["images"]) for v in split.values()
                         if isinstance(v, dict) and "images" in v))


def dev_question_ids() -> set[str]:
    return set(_json(SPLIT_FILE)["public_dev"]["questions"])


def set_t_images() -> list[str]:
    return _json(SET_T)["images"]


def targets() -> list[tuple[str, str]]:
    """(image_id, split) for every image to label now: public_dev, then set T."""
    return ([(i, "public_dev") for i in sorted(dev_images())]
            + [(i, "train") for i in set_t_images()])


def image_path(image_id: str, split: str) -> Path:
    folder = {"train": TRAIN_IMAGES, "public_dev": PUBLIC_IMAGES}[split]
    hits = sorted(glob.glob(str(folder / f"{glob.escape(image_id)}.*")))
    if not hits:
        raise FileNotFoundError(f"no image file for {image_id} in {folder}")
    return Path(hits[0])


def violation_images() -> set[str]:
    """public_dev and train images with a violation question ("vi phạm")."""
    dev_q = dev_question_ids()
    out = {q["image_id"] for q in _json(TRAIN_QA) if VIOLATION_RE.search(q["question"])}
    out |= {q["image_id"] for q in _json(PUBLIC_QA)
            if q["id"] in dev_q and VIOLATION_RE.search(q["question"])}
    return out


# --------------------------------------------------------------------------- select

def excluded_train_images(public: set[str], groups: list[dict]) -> set[str]:
    """Train images in a duplicate group that also holds one of the given public
    images (both halves of the public test). Private duplicates are not excluded."""
    out: set[str] = set()
    for g in groups:
        imgs = g["images"]
        if any(i["split"] == "public" and i["image_id"] in public for i in imgs):
            out |= {i["image_id"] for i in imgs if i["split"] == "train"}
    return out


def pick_set_t(train_images: list[str], train_questions: list[dict], public: set[str],
               groups: list[dict], n: int = SET_T_SIZE, seed: int = SEED) -> list[str]:
    """n train images in no duplicate group with a public image, taken round-robin over
    rough question categories (each category shuffled with the seed), so a small
    set covers many sign kinds. Deterministic for the same inputs."""
    banned = excluded_train_images(public, groups)
    first_q: dict[str, dict] = {}
    for q in sorted(train_questions, key=lambda q: q["id"]):
        first_q.setdefault(q["image_id"], q)
    pool = sorted(i for i in set(train_images) if i not in banned)
    by_cat: dict[str, list[str]] = {}
    for i in pool:
        cat = category(first_q[i]["question"]) if i in first_q else "no_question"
        by_cat.setdefault(cat, []).append(i)
    rng = random.Random(seed)
    for name in sorted(by_cat):
        rng.shuffle(by_cat[name])
    picked: list[str] = []
    while len(picked) < n and any(by_cat.values()):
        for name in sorted(by_cat):
            if by_cat[name] and len(picked) < n:
                picked.append(by_cat[name].pop(0))
    return sorted(picked, key=_id_key)


def _id_key(image_id: str) -> tuple:
    return tuple(int(p) if p.isdigit() else p for p in image_id.split("_"))


def select(n: int = SET_T_SIZE) -> list[str]:
    train_images = sorted(p.stem for p in TRAIN_IMAGES.iterdir() if not p.name.startswith("."))
    dups = _json(DUPLICATES)
    public = public_images()
    banned = excluded_train_images(public, dups["groups"])
    picked = pick_set_t(train_images, _json(TRAIN_QA), public, dups["groups"], n)
    SET_T.write_text(json.dumps({
        "seed": SEED, "n": len(picked),
        "method": ("train images in no duplicate group (data/splits/duplicates.json) with any "
                   "public test image (ids from public_split.json), round-robin over rough question categories, each "
                   "category shuffled with random.Random(seed)"),
        "excluded_train_images": len(banned),
        "pool": len(set(train_images) - banned),
        "images": picked}, indent=2) + "\n", encoding="utf-8")
    print(f"set T: {len(picked)} train images -> {SET_T.relative_to(ROOT)} "
          f"({len(banned)} excluded, pool {len(set(train_images) - banned)})")
    return picked


# --------------------------------------------------------------------------- images

def native_size(w: int, h: int) -> tuple[int, int]:
    """Size the image is sent at: long edge <= 1568 px, area <= ~1.15 MP, never upscaled."""
    s = min(1.0, NATIVE_LONG_EDGE / max(w, h), (NATIVE_MAX_PIXELS / (w * h)) ** 0.5)
    return max(1, round(w * s)), max(1, round(h * s))


def image_tokens(w: int, h: int) -> int:
    nw, nh = native_size(w, h)
    return int(nw * nh / 750) + 1


def image_block(path: Path) -> dict:
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im = im.resize(native_size(*im.size), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode()}}


# --------------------------------------------------------------------------- prompt

def catalog_listing() -> str:
    lines = ["code | name (vi) | shape / border / background", "--- | --- | ---"]
    for s in load_catalog().signs:
        v = s.visual
        lines.append(f"{s.code} | {s.name_vi} | {v.shape} / {v.border} / {v.background}")
    return "\n".join(lines)


def prefill_system() -> str:
    guide = GUIDE.read_text(encoding="utf-8").strip()
    return (
        "You draft gold sign labels for Vietnamese road images. A person will check every "
        "sign against the image afterwards, so list what you see, and mark a sign "
        "readable: false rather than guess.\n\n"
        "Reply with one JSON object only, no prose: "
        '{"signs": [...], "vehicles": [...], "notes": "..."}. Each sign has the fields of '
        "the guide's table (code, readable, value, unit, shape, border, background, "
        "position, plates, rules, lanes). Leave out fields that don't apply. List vehicles "
        "only if the user turn says the image has a violation question.\n\n"
        f"## Labelling guide\n\n{guide}\n\n## Sign catalog\n\n{catalog_listing()}\n")


def prompt_hash() -> str:
    return hashlib.sha256(prefill_system().encode("utf-8")).hexdigest()[:12]


def user_text(violation: bool) -> str:
    return ("Label the signs in this image."
            + (" The image has a violation question: list its vehicles too." if violation else ""))


def rough_tokens(text: str) -> int:
    return int(len(text.encode("utf-8")) / BYTES_PER_TOKEN) + 1


# --------------------------------------------------------------------------- estimate

def measured_system_tokens(model: str | None = None) -> int | None:
    """The system prompt's size as a cache read in an earlier draft with the current
    prompt (by any model if `model` is None; tokenizers may differ by model)."""
    reads = [d["usage"]["cache_read_tokens"] for d in load_drafts().values()
             if d.get("prompt_sha") == prompt_hash() and (model is None or d.get("model") == model)
             and (d.get("usage") or {}).get("cache_read_tokens")]
    return max(reads) if reads else None


def estimate(sdk=None, model: str = MODEL, remaining: bool = False) -> dict:
    """Pre-fill cost for public_dev + set T (only the images not drafted yet, with
    `remaining`). With an SDK client, prompt sizes come from messages.count_tokens
    (free, but an API call); without, the system prompt's size is taken from an
    earlier draft's cache read when there is one, else from its bytes, and images
    from their pixel size. Never sends a message."""
    from PIL import Image

    system = prefill_system()
    sys_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    viol = violation_images()
    drafted = load_drafts() if remaining else {}
    todo = [(i, s) for i, s in targets() if i not in drafted]
    measured = measured_system_tokens()
    sys_rough = measured or rough_tokens(system)
    counts = []
    for image_id, split in todo:
        path = image_path(image_id, split)
        if sdk is not None:
            msg = [{"role": "user", "content": [image_block(path),
                                                {"type": "text", "text": user_text(image_id in viol)}]}]
            counts.append(sdk.messages.count_tokens(model=model, system=sys_blocks, messages=msg,
                                                    output_config={"effort": EFFORT}).input_tokens)
        else:
            with Image.open(path) as im:
                w, h = im.size
            counts.append(sys_rough + image_tokens(w, h) + rough_tokens(user_text(image_id in viol)))
    if sdk is not None:
        method = "exact (messages.count_tokens)"
    elif measured:
        method = (f"rough (system: {measured} tokens, measured as a cache read in an earlier draft; "
                  "images: w x h / 750 at native size)")
    else:
        method = f"rough (system: bytes / {BYTES_PER_TOKEN}; images: w x h / 750 at native size)"
    n, prompt = len(counts), sum(counts)
    sys_tokens = sys_rough if sdk is None else min(counts) - 400
    out = EXPECTED_OUTPUT_TOKENS * n
    # Priced call by call: Haiku 5.5's long-prompt rate applies per request (> 100K
    # prompt tokens), so pricing summed totals as one request would wrongly trigger it.
    o = EXPECTED_OUTPUT_TOKENS

    def call(k: int, c: int, out_tokens: int) -> float:
        cached = {"cache_write_tokens": sys_tokens} if k == 0 else {"cache_read_tokens": sys_tokens}
        return cost_usd(model, input_tokens=c - sys_tokens, output_tokens=out_tokens, **cached)

    sequential = sum(call(k, c, o) for k, c in enumerate(counts))
    double = sum(call(k, c, 2 * o) for k, c in enumerate(counts))
    no_cache = sum(cost_usd(model, input_tokens=c, output_tokens=o) for c in counts)
    return {
        "method": method, "model": model, "effort": EFFORT, "max_tokens": MAX_TOKENS,
        "prefill_version": PREFILL_VERSIONS[model], "prompt_sha": prompt_hash(),
        "images": n, "already_drafted": len(drafted),
        "public_dev": sum(s == "public_dev" for _, s in todo), "set_t": sum(s == "train" for _, s in todo),
        "system_tokens": sys_tokens, "prompt_tokens_total": prompt,
        "expected_output_tokens_total": out, "expected_output_tokens_per_image": EXPECTED_OUTPUT_TOKENS,
        "sequential_expected_usd": round(sequential, 4),
        "sequential_expected_usd_double_output": round(double, 4),
        "no_cache_usd": round(no_cache, 4),
        "worst_case_usd": round(sum(worst_case_usd(model, c, MAX_TOKENS) for c in counts), 4),
        "worst_case_usd_per_call": round(max((worst_case_usd(model, c, MAX_TOKENS) for c in counts),
                                             default=0.0), 4),
    }


# --------------------------------------------------------------------------- prefill

class CacheMiss(SystemExit):
    pass


def drafts_path() -> Path:
    return WORK / "drafts.jsonl"


def load_drafts() -> dict[str, dict]:
    p = drafts_path()
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["image_id"]] = rec
    return out


def _usage(u) -> dict:
    return {"input_tokens": u.input_tokens or 0, "output_tokens": u.output_tokens or 0,
            "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0}


def _log_http_error(run_id: str, image_id: str, call: str, e: Exception, model: str = MODEL) -> None:
    """Log a failed request with cost 0, as LLMClient.json_reply does."""
    log_call({"run_id": run_id, "purpose": "gold-sign pre-fill", "model": model, "batch": False,
              "effort": EFFORT, "status": "http_error", "image_id": image_id, "call": call,
              "cost_usd": 0.0, "http_status": getattr(e, "status_code", None),
              "request_id": getattr(e, "request_id", None), "error": str(e)[:500]})


def prefill(max_spend: float, sdk=None, check_at: int = 2,
            min_cache_share: float = MIN_CACHE_SHARE, model: str = MODEL) -> dict[str, dict]:
    """Draft labels one image at a time (public_dev and set T only), like
    gold_intents.run: each call's worst case is checked by the spend guard before it
    is sent, every call is logged, progress resumes, and the run stops after call
    `check_at` if less than `min_cache_share` of the prompt came from the cache.
    Images drafted earlier, by any model, are not drafted again."""
    if model not in PREFILL_VERSIONS:
        raise SystemExit(f"unknown pre-fill model {model!r}; one of {', '.join(MODELS)}")
    version = PREFILL_VERSIONS[model]
    if sdk is None:
        import anthropic
        sdk = anthropic.Anthropic()
    guard = SpendGuard(max_spend)
    run_id = hashlib.sha256(os.urandom(8)).hexdigest()[:12]
    WORK.mkdir(parents=True, exist_ok=True)
    system = prefill_system()
    sys_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    kw = {"output_config": {"effort": EFFORT}}
    viol = violation_images()
    done = load_drafts()
    todo = [(i, s) for i, s in targets() if i not in done]
    print(f"{len(done)} already drafted, {len(todo)} to go with {model} ({version}, "
          f"limit ${max_spend:.2f})")
    for n, (image_id, split) in enumerate(todo, 1):
        msg = [{"role": "user", "content": [image_block(image_path(image_id, split)),
                                            {"type": "text", "text": user_text(image_id in viol)}]}]
        try:
            counted = sdk.messages.count_tokens(model=model, system=sys_blocks, messages=msg, **kw)
        except Exception as e:
            _log_http_error(run_id, image_id, "count_tokens", e, model)
            raise
        guard.check(worst_case_usd(model, counted.input_tokens, MAX_TOKENS), f"pre-fill {image_id}")
        try:
            resp = sdk.messages.create(model=model, max_tokens=MAX_TOKENS, system=sys_blocks,
                                       messages=msg, **kw)
        except Exception as e:
            _log_http_error(run_id, image_id, "create", e, model)
            raise
        usage = _usage(resp.usage)
        cost = cost_usd(model, **usage)
        guard.add(cost)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        rec: dict[str, Any] = {"image_id": image_id, "split": split, "model": model,
                               "prefill_version": version, "prompt_sha": prompt_hash(),
                               "stop_reason": resp.stop_reason, "raw_reply": text, "usage": usage,
                               "draft": None, "errors": []}
        if resp.stop_reason == "refusal":
            rec["status"] = "refused"
        elif resp.stop_reason == "max_tokens":
            rec["status"], rec["errors"] = "truncated", [f"cut off at max_tokens={MAX_TOKENS}"]
        else:
            try:
                rec["draft"] = parse_json_reply(text)
                rec["errors"] = check_label({
                    "image_id": image_id, "split": split, "status": "done",
                    "violation_question": image_id in viol,
                    "signs": rec["draft"].get("signs", []),
                    "vehicles": rec["draft"].get("vehicles", [])})[1]
                rec["status"] = "invalid" if rec["errors"] else "ok"
            except LLMBadJSON as e:
                rec["status"], rec["errors"] = "bad_json", [str(e)]
        log_call({"run_id": run_id, "purpose": "gold-sign pre-fill", "model": model, "batch": False,
                  "effort": EFFORT, "status": rec["status"], "prefill_version": version, "image_id": image_id,
                  "request_id": getattr(resp, "_request_id", None), "stop_reason": resp.stop_reason,
                  **usage, "cost_usd": round(cost, 6)})
        with open(drafts_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        done[image_id] = rec
        print(f"[{n}/{len(todo)}] {image_id}: {rec['status']}  spent ${guard.spent:.2f}")
        if n == check_at:
            prompt = usage["input_tokens"] + usage["cache_read_tokens"] + usage["cache_write_tokens"]
            share = usage["cache_read_tokens"] / prompt if prompt else 0.0
            if share < min_cache_share:
                raise CacheMiss(f"call {n} read only {share:.0%} of its {prompt} prompt tokens from "
                                f"the cache (need {min_cache_share:.0%}); stopped after "
                                f"${guard.spent:.2f}. Progress is saved.")
    print(f"done: {len(done)} drafts, this run spent ${guard.spent:.2f}")
    return done


# --------------------------------------------------------------------------- sheet

def label_path(image_id: str, split: str) -> Path:
    return WORK / "labels" / split / f"{image_id}.yaml"


VEHICLE_CLASSES = {c.value for c in VehicleClass}
SIGN_FIELDS = set(Sign.model_fields) | SIGN_EXTRA_KEYS


def _fix_vehicles(items: Any) -> tuple[Any, int]:
    """Bare strings that are VehicleClass values become {class: ...}; anything
    else is left as it is (and flagged by validation)."""
    if not isinstance(items, list):
        return items, 0
    out, n = [], 0
    for v in items:
        if isinstance(v, str) and v in VEHICLE_CLASSES:
            out.append({"class": v})
            n += 1
        else:
            out.append(v)
    return out, n


def clean_sign(raw: Any) -> tuple[Any, list[str], int]:
    """Lossless, mechanical clean-up of one drafted sign for the label YAML.

    1. Vehicles given as a bare VehicleClass string, in plates, plate condition
       groups, the sign's condition groups and lane rows, become {class: ...}.
    2. Text fields that are not sign fields (notes, notes_text, notes_on_sign,
       text, ...) are moved out of the sign into comment lines, verbatim.

    Returns (sign, comment lines, number of vehicle fixes). Nothing else changes."""
    if not isinstance(raw, dict):
        return raw, [], 0
    sign, comments, n = dict(raw), [], 0
    for k in [k for k in sign if k not in SIGN_FIELDS and isinstance(sign[k], str)]:
        comments.append(f"draft {k}: {sign.pop(k)}")
    for key in ("plates", "rules", "lanes"):
        if not isinstance(sign.get(key), list):
            continue
        items = []
        for it in sign[key]:
            if isinstance(it, dict):
                it = dict(it)
                if "vehicles" in it:
                    it["vehicles"], k = _fix_vehicles(it["vehicles"])
                    n += k
                if key == "plates" and isinstance(it.get("rules"), list):
                    groups = []
                    for g in it["rules"]:
                        if isinstance(g, dict) and "vehicles" in g:
                            g = dict(g)
                            g["vehicles"], k = _fix_vehicles(g["vehicles"])
                            n += k
                        groups.append(g)
                    it["rules"] = groups
            items.append(it)
        sign[key] = items
    return sign, comments, n


def sign_errors(sign: Any, image_id: str, split: str) -> list[str]:
    """Validation errors of one sign, without the image and sign prefix."""
    _, errs = check_label({"image_id": image_id, "split": split, "status": "todo", "signs": [sign]})
    return [re.sub(r"^\S+ sign 1: ", "", e) for e in errs]


def vehicle_errors(doc: dict) -> list[str]:
    _, errs = check_label({**doc, "signs": [], "status": "todo"})
    return errs


def _comment(lines: list[str], indent: str) -> str:
    out = []
    for line in lines:
        parts = str(line).splitlines() or [""]
        out.append(f"{indent}# {parts[0]}")
        out += [f"{indent}#   {p}" for p in parts[1:]]
    return "".join(x + "\n" for x in out)


def _dump(obj: Any) -> str:
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, width=100)


def label_yaml(doc: dict, sign_comments: list[list[str]]) -> str:
    """The label file text: the document as YAML, with each sign's comment lines
    (moved draft text, then "needs fix: ..." lines) right above that sign."""
    head = {k: doc[k] for k in ("image_id", "split", "status", "violation_question")}
    out = _dump(head)
    if doc["signs"]:
        out += "signs:\n"
        for sign, comments in zip(doc["signs"], sign_comments):
            out += _comment(comments, "  ")
            out += "".join("  " + line + "\n" for line in _dump([sign]).splitlines())
    else:
        out += "signs: []\n"
    veh = vehicle_errors(doc)
    out += _comment([f"needs fix: {e}" for e in veh], "")
    out += _dump({"vehicles": doc["vehicles"], "notes": doc["notes"]})
    return out


def draft_doc(image_id: str, split: str, draft: dict, violation: bool) -> tuple[dict, list[list[str]], int]:
    """A label document from a draft, after clean_sign, with the comment lines per
    sign (moved text, then needs-fix lines for what the clean-up does not fix)."""
    signs, comments, fixes = [], [], 0
    for raw in draft.get("signs") or []:
        sign, moved, n = clean_sign(raw)
        fixes += n
        signs.append(sign)
        comments.append(moved + [f"needs fix: {e}" for e in sign_errors(sign, image_id, split)])
    vehicles, n = _fix_vehicles(draft.get("vehicles") or []) if violation else ([], 0)
    doc = {"image_id": image_id, "split": split, "status": "todo", "violation_question": violation,
           "signs": signs, "vehicles": vehicles, "notes": draft.get("notes", "") or ""}
    return doc, comments, fixes + n


def file_needs_fix(doc: dict) -> list[str]:
    """Needs-fix lines for a label file as it is now (owner edits included)."""
    iid, split = doc.get("image_id", "?"), doc.get("split", "train")
    out = []
    for k, sign in enumerate(doc.get("signs") or [], 1):
        code = sign.get("code") if isinstance(sign, dict) else None
        out += [f"sign {k} ({code}): needs fix: {e}" for e in sign_errors(sign, iid, split)]
    out += [f"needs fix: {e}" for e in vehicle_errors(
        {**doc, "signs": [], "vehicles": doc.get("vehicles") or []})]
    return out


def sheet() -> dict:
    """One YAML label file per image (from its draft, after the format clean-up)
    and a local sheet.html that shows each image next to its file, with a visible
    "needs fix" line for every error the clean-up does not fix. drafts.jsonl is
    only read. Existing YAML files are never overwritten; the sheet shows their
    current content. Images are linked from the dataset folder, never copied."""
    drafts, viol = load_drafts(), violation_images()
    written, rows = [], []
    stats = {"images": 0, "written": 0, "kept_existing": 0, "vehicle_fixes": 0, "moved_fields": 0,
             "valid": 0, "need_fix": 0}
    for image_id, split in targets():
        stats["images"] += 1
        p = label_path(image_id, split)
        if p.exists():
            stats["kept_existing"] += 1
        else:
            d = (drafts.get(image_id) or {}).get("draft") or {}
            doc, comments, fixes = draft_doc(image_id, split, d, image_id in viol)
            stats["vehicle_fixes"] += fixes
            stats["moved_fields"] += sum(1 for c in comments for x in c if x.startswith("draft "))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(label_yaml(doc, comments), encoding="utf-8")
            written.append(p)
        text = p.read_text(encoding="utf-8")
        flags = file_needs_fix(yaml.safe_load(text) or {})
        stats["need_fix" if flags else "valid"] += 1
        img = image_path(image_id, split).resolve().as_uri()
        fix_html = "".join(f"<li>{html.escape(f)}</li>" for f in flags)
        rows.append(f"<section><h2>{html.escape(image_id)} <small>{split}"
                    f"{' · violation question' if image_id in viol else ''}</small></h2>"
                    f"<img src='{img}' loading='lazy'><div><p><a href='{p.resolve().as_uri()}'>"
                    f"{html.escape(_rel(p))}</a></p>"
                    + (f"<ul class='fix'>{fix_html}</ul>" if flags else "<p class='ok'>no format errors</p>")
                    + f"<pre>{html.escape(text)}</pre></div></section>")
    (WORK / "sheet.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Gold signs</title><style>"
        "body{font:14px system-ui;margin:16px}section{display:grid;grid-template-columns:"
        "minmax(0,1fr) minmax(0,1fr);gap:12px;border-top:1px solid #ccc;padding:12px 0}"
        "h2{grid-column:1/-1;margin:0}p{margin:0 0 6px}img{max-width:100%}"
        "pre{white-space:pre-wrap;margin:0}.fix{color:#b00020;font-weight:600;margin:0 0 6px}"
        ".ok{color:#1b7a2f}</style>"
        f"<p>{stats['valid']} of {stats['images']} label files have no format errors; "
        f"{stats['need_fix']} need a fix.</p>" + "".join(rows), encoding="utf-8")
    print(f"{len(written)} new label files ({stats['kept_existing']} kept), "
          f"{stats['need_fix']} need a fix, sheet -> {_rel(WORK / 'sheet.html')}")
    stats["written"] = len(written)
    return stats


# --------------------------------------------------------------------------- validation

def check_sign_code(code: Any, readable: bool, local_notice: bool = False) -> str | None:
    if not isinstance(code, str) or not code:
        return "code is missing"
    if local_notice:
        return None if code == "UNKNOWN" else "a local_notice has code: UNKNOWN (it is not a QCVN 41 sign)"
    if code == "UNKNOWN":
        return None if not readable else ("UNKNOWN is only allowed with readable: false, or with "
                                          "local_notice for a standalone local notice")
    cat = load_catalog()
    if cat.has(code):
        return None
    try:
        rows = cat.codes_matching(code)
    except KeyError:
        return f"unknown sign code {code!r}"
    if len(rows) > 1:
        return f"{code!r} names several catalog rows ({', '.join(rows)}); give the variant"
    return None


def _loc(err: dict) -> str:
    loc = ".".join(map(str, err["loc"]))
    return f"{loc}: " if loc else ""


def _rel(p: Path) -> str:
    p = Path(p)
    return str(p.relative_to(ROOT)) if p.resolve().is_relative_to(ROOT) else str(p)


def check_label(doc: dict) -> tuple[dict | None, list[str]]:
    """Validate one label document. Returns (gold record, errors)."""
    errs: list[str] = []
    iid = doc.get("image_id", "?")
    if extra := set(doc) - LABEL_KEYS:
        errs.append(f"{iid}: unknown fields {sorted(extra)}")
    if doc.get("split") not in SPLITS:
        errs.append(f"{iid}: split must be one of {SPLITS}")
    if doc.get("status") not in STATUSES:
        errs.append(f"{iid}: status must be one of {STATUSES}")
    signs, vehicles = doc.get("signs") or [], doc.get("vehicles") or []
    if not isinstance(signs, list) or not isinstance(vehicles, list):
        return None, errs + [f"{iid}: signs and vehicles must be lists"]
    out_signs = []
    for k, raw in enumerate(signs, 1):
        where = f"{iid} sign {k}"
        if not isinstance(raw, dict):
            errs.append(f"{where}: not a mapping")
            continue
        readable = raw.get("readable", True)
        if not isinstance(readable, bool):
            errs.append(f"{where}: readable must be true or false")
            readable = True
        notice = raw.get("local_notice")
        if notice is not None:
            if not isinstance(notice, str) or not notice.strip():
                errs.append(f"{where}: local_notice must be the notice's text, verbatim")
            if not readable:
                errs.append(f"{where}: a local_notice is readable; use readable: false without it")
            if bad := [f for f in LOCAL_NOTICE_FORBIDS if raw.get(f)]:
                errs.append(f"{where}: a local_notice keeps its text in local_notice, "
                            f"not in {', '.join(bad)}")
        if e := check_sign_code(raw.get("code"), readable, notice is not None):
            errs.append(f"{where}: {e}")
        if (raw.get("position") or {}).get("box") is not None:
            errs.append(f"{where}: gold has no pixel boxes")
        fields = {k2: v for k2, v in raw.items() if k2 not in SIGN_EXTRA_KEYS}
        try:
            s = Sign.model_validate({"id": f"s{k}", **fields})
        except ValidationError as e:
            errs += [f"{where}: {_loc(x)}{x['msg']}" for x in e.errors()]
            continue
        out_signs.append({"readable": readable,
                          **({"local_notice": str(notice).strip()} if notice is not None else {}),
                          **s.model_dump(mode="json", by_alias=True, exclude_defaults=True)})
    if vehicles and doc.get("split") == "private":
        errs.append(f"{iid}: private labels have no vehicles")
    elif vehicles and not doc.get("violation_question"):
        errs.append(f"{iid}: vehicles only on images with a violation question")
    out_vehicles = []
    for k, raw in enumerate(vehicles, 1):
        try:
            v = SceneVehicle.model_validate({"id": f"v{k}", **(raw if isinstance(raw, dict) else {})})
            out_vehicles.append(v.model_dump(mode="json", by_alias=True, exclude_defaults=True))
        except ValidationError as e:
            errs += [f"{iid} vehicle {k}: {_loc(x)}{x['msg']}" for x in e.errors()]
    if errs:
        return None, errs
    return {"image_id": iid, "split": doc["split"], "signs": out_signs, "vehicles": out_vehicles,
            "violation_question": bool(doc.get("violation_question")),
            "notes": doc.get("notes") or ""}, []


# --------------------------------------------------------------------------- import

def is_gitignored(path: Path) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT, capture_output=True)
    return r.returncode == 0


def existing_gold_ids(path: Path) -> list[str]:
    """Image ids of the gold file already at `path` (empty if there is none)."""
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line)["image_id"] for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def write_atomic(path: Path, text: str) -> None:
    """Write via a temp file in the same folder, then rename over the target, so a
    crash never leaves a truncated file. The temp file is removed on failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_gold(rows: list[dict], path: Path, replace: bool = False) -> Path:
    """Write gold rows.

    - Nothing is written when there are no rows.
    - A file with fewer rows than the gold file already at `path`, or one that
      drops any of its image ids, is refused unless `replace` is set; what would be
      lost is printed.
    - Private rows go only to PRIVATE_GOLD, and only if git ignores it; public and
      private rows are never mixed in one file.
    - The write is atomic (temp file, then rename)."""
    if not rows:
        raise SystemExit("refusing to write a gold file with 0 labels; nothing was written")
    private = [r for r in rows if r["split"] == "private"]
    if private and len(private) != len(rows):
        raise SystemExit("refusing to mix private and non-private labels in one file")
    path = Path(path)
    if private:
        if path.resolve() != PRIVATE_GOLD.resolve():
            raise SystemExit(f"refusing to write private labels to {path}; they go only to "
                             f"{PRIVATE_GOLD.relative_to(ROOT)}")
        if not is_gitignored(path):
            raise SystemExit(f"refusing to write private labels: git does not ignore {path}")
    elif path.resolve().is_relative_to(PRIVATE_OUT.resolve()):
        raise SystemExit("non-private labels don't go in the private folder")
    old = existing_gold_ids(path)
    lost = sorted(set(old) - {r["image_id"] for r in rows}, key=_id_key)
    if (len(rows) < len(old) or lost) and not replace:
        msg = [f"refusing to replace {_rel(path)}: it has {len(old)} rows, the new file {len(rows)}"]
        if lost:
            msg.append(f"{len(lost)} image ids would be lost: {', '.join(lost)}")
        msg.append("nothing was written; pass --replace to write it anyway")
        raise SystemExit("\n".join(msg))
    if lost:
        print(f"--replace: dropping {len(lost)} image ids from {_rel(path)}: {', '.join(lost)}")
    write_atomic(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return path


def _sign_key(s: dict) -> str:
    return json.dumps({k: v for k, v in s.items() if k != "id"}, sort_keys=True, ensure_ascii=False)


def anchoring(final: list[dict], draft: dict | None) -> dict | None:
    """How many final signs equal a draft sign exactly (the pre-fill anchoring figure)."""
    if not draft:
        return None
    rec, errs = check_label({"image_id": "draft", "split": "train", "status": "done",
                             "signs": draft.get("signs", [])})
    if errs:
        return {"draft_signs": len(draft.get("signs", [])), "kept_unchanged": 0, "draft_valid": False}
    pool = [_sign_key(s) for s in rec["signs"]]
    kept = 0
    for s in final:
        k = _sign_key(s)
        if k in pool:
            pool.remove(k)
            kept += 1
    return {"draft_signs": len(rec["signs"]), "kept_unchanged": kept, "draft_valid": True}


def import_labels(private: bool = False, labels_dir: Path | None = None,
                  out: Path | None = None, replace: bool = False) -> list[dict]:
    if private:
        labels_dir, out = labels_dir or PRIVATE_OUT / "labels", out or PRIVATE_GOLD
        allowed = None
    else:
        labels_dir, out = labels_dir or WORK / "labels", out or GOLD
        allowed = {**{i: "public_dev" for i in dev_images()}, **{i: "train" for i in set_t_images()}}
    drafts = load_drafts()
    gold, problems, rejected = [], [], set()
    statuses: dict[str, int] = {}
    for p in sorted(Path(labels_dir).rglob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        st = doc.get("status") if doc.get("status") in STATUSES else "other"
        statuses[st] = statuses.get(st, 0) + 1
        if doc.get("status") != "done":
            continue
        n_problems = len(problems)
        if private and doc.get("split") != "private":
            problems.append(f"{p.name}: only split: private belongs in the private folder")
            continue
        if not private and doc.get("split") == "private":
            problems.append(f"{p.name}: private labels are imported with --private only")
            continue
        if allowed is not None and allowed.get(doc.get("image_id")) != doc.get("split"):
            problems.append(f"{p.name}: {doc.get('image_id')} is not a {doc.get('split')} image "
                            "of the gold sets (public_dev or set T)")
            continue
        rec, errs = check_label(doc) if len(problems) == n_problems else (None, [])
        problems += errs
        if len(problems) > n_problems:
            rejected.add(p.name)
            continue
        d = {} if private else (drafts.get(rec["image_id"]) or {})
        rec["draft_model"] = d.get("model")              # None: labelled without a draft
        rec["prefill_version"] = d.get("prefill_version")
        rec["anchoring"] = anchoring(rec["signs"], d.get("draft")) if d else None
        gold.append(rec)
    print(f"label files: {statuses.get('done', 0)} done ({len(gold)} accepted, {len(rejected)} rejected), "
          f"{statuses.get('todo', 0)} todo, {statuses.get('skip', 0)} skip"
          + (f", {statuses['other']} with no valid status" if statuses.get("other") else ""))
    if problems:
        raise SystemExit(f"{len(rejected)} label files rejected; nothing was written:\n" + "\n".join(problems))
    gold.sort(key=lambda r: (r["split"], _id_key(r["image_id"])))
    write_gold(gold, out, replace=replace)
    print(f"{len(gold)} labelled images -> {Path(out).relative_to(ROOT) if Path(out).is_relative_to(ROOT) else out}")
    if not private:
        rows = visual_review_rows(gold)
        print(f"rows for the visual check (D10): {len(rows)}\n  " + ", ".join(rows))
    return gold


# --------------------------------------------------------------------------- D10 list

CODE_RE = re.compile(r"\b((?:P|DP|R|W|IE|I|S)\.[0-9]{3}[a-z]?)")


def _rows_named(texts) -> set[str]:
    cat, out = load_catalog(), set()
    for t in texts:
        for c in CODE_RE.findall(t):
            try:
                out |= {cat.get(r).code for r in cat.codes_matching(c)}
            except KeyError:
                pass
    return out


def visual_review_rows(gold: list[dict]) -> list[str]:
    """Catalog rows to check visually before prompts/scene/v1 is frozen (plan D10):
    rows in the set-T gold, in tests/fixtures/train_*.json and in train question
    text. Not the public_dev gold."""
    cat = load_catalog()
    rows = {cat.get(r).code for g in gold if g["split"] == "train"
            for s in g["signs"] if s["code"] != "UNKNOWN" for r in cat.codes_matching(s["code"])}
    rows |= _rows_named(Path(p).read_text(encoding="utf-8")
                        for p in glob.glob(str(ROOT / "tests" / "fixtures" / "train_*.json")))
    if TRAIN_QA.exists():
        rows |= _rows_named(q["question"] for q in _json(TRAIN_QA))
    order = [s.code for s in cat.signs]
    return sorted(rows, key=order.index)


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("--n", type=int, default=SET_T_SIZE)
    e = sub.add_parser("estimate")
    e.add_argument("--model", choices=MODELS, default=MODEL)
    e.add_argument("--remaining", action="store_true", help="only images not drafted yet")
    e.add_argument("--count", action="store_true",
                   help="exact prompt sizes from messages.count_tokens (needs ANTHROPIC_API_KEY)")
    p = sub.add_parser("prefill")
    p.add_argument("--max-spend", type=float, required=True)
    p.add_argument("--model", choices=MODELS, default=MODEL)
    sub.add_parser("sheet")
    i = sub.add_parser("import")
    i.add_argument("--private", action="store_true")
    i.add_argument("--replace", action="store_true",
                   help="allow a gold file with fewer rows or fewer image ids than the existing one")
    a = ap.parse_args()
    if a.cmd == "select":
        select(a.n)
    elif a.cmd == "estimate":
        sdk = None
        if a.count:
            import anthropic
            sdk = anthropic.Anthropic()
        print(json.dumps(estimate(sdk, model=a.model, remaining=a.remaining), indent=2))
    elif a.cmd == "prefill":
        prefill(a.max_spend, model=a.model)
    elif a.cmd == "sheet":
        sheet()
    elif a.cmd == "import":
        import_labels(private=a.private, replace=a.replace)


if __name__ == "__main__":
    main()
