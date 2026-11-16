"""The two-pass fallback (docs/plans/phase-3.md, item 7; approved by the owner on
2026-11-16).

It runs after pass 1 (the scene call, verification and the D8 re-run), on what
pass 1 returned and the image's own pixels only: never a file name, image id or
anything outside the image.

A1, region pass (dense scenes), first:
- trigger: pass 1 lists >= DENSE_MIN_SIGNS signs;
- a 2 x 2 tile grid over the original image, the tiles overlapping by 20% of a
  tile's size, each enlarged up to the scene prep's limits (long edge 1568 px,
  area ~1.15 MP) and read with the v4-tile prompt;
- a tile sign whose box overlaps a pass-1 sign (IoU >= 0.3, or its centre inside
  the pass-1 box) is dropped; tile signs are deduplicated among themselves the same
  way (the more confident one is kept, then the earlier tile);
- the remaining tile signs are added at `low`.
- Ranks (owner's change 1, option B "shift"): an added sign takes its top-down
  place by box top; pass-1 signs below it move down by one. Pass-1 relative order
  and pass-1 sides never change and tied pass-1 ranks stay tied. Only added signs
  get a side, from their box centre against the image centre.

A2, box crops (unsure codes), second, so it also re-reads the signs A1 added:
- trigger: a sign that is `low` or `UNKNOWN` and has a box;
- the crop: the box on the original, widened by 50% of its width on each side, 50%
  of its height above and 100% below, at least 128 px on the short side, clipped to
  the image, then enlarged to 384 px on the short side; read with the v4-crop prompt;
- the reading is combined with pass 1 by a policy (see `combine`); the set-T
  comparison picks the one frozen for checkpoint 2.

The scene is verified again at the end (values, looks, plates), as the re-run's
merge does. Tile and crop replies go to the scene cache under image hash + model +
effort + prompt version + box (vqa/perception/cache.py, `region_key`). A reply that
is not one JSON object gets one retry that sends only the error (D4, owner 2026-11-16).
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Any, Callable

from vqa.kb import Catalog, load_catalog
from vqa.llm.client import LLMBadJSON, LLMRefusal, LLMTruncated, parse_json_reply
from vqa.perception import prompt as scene_prompt
from vqa.perception.cache import RegionRecord, SceneCache
from vqa.perception.image import JPEG_QUALITY, LONG_EDGE, MAX_PIXELS, PreparedImage
from vqa.perception.matching import row_of
from vqa.perception.verify import verify
from vqa.perception.wire import resolve_code, retry_messages, to_scene
from vqa.schemas import AltReading, Confidence, SceneGraph, Side, Sign

DENSE_MIN_SIGNS = 5
TILE_GRID = 2
TILE_OVERLAP = 0.20
DEDUP_IOU = 0.30
CROP_MARGIN = {"left": 0.5, "top": 0.5, "right": 0.5, "bottom": 1.0}
CROP_MIN_SHORT = 128
CROP_UPSCALE_SHORT = 384
POLICIES = ("rules", "crop_always", "crop_high", "never")
# The combining rule frozen for checkpoint 2 (owner's rule, 2026-11-16: the best mean code
# F1 over both models on set T, but the approved "rules" if within 1 point of it). Set T,
# development, in-sample, after the crop retry (Sonnet repair run 7ea7aa8dcc8f, no crop
# left unread): crop_always 76.10%, rules 74.83% (1.27 points behind): "crop_always".
# (Before the retry, with 26 of Sonnet's 56 crops unread, rules was kept at 0.86 behind.)
CHOSEN_POLICY = "crop_always"
_RANK = {Confidence.high: 0, Confidence.medium: 1, Confidence.low: 2}

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class FallbackConfig:
    tile_version: str = "v4-tile"
    crop_version: str = "v4-crop"
    policy: str = CHOSEN_POLICY
    tiles: bool = True
    crops: bool = True
    # T4 (owner, 2026-11-16; tuned on public_dev): when a crop agrees with pass 1's main
    # code, pass 1's own alternative reading for that sign is dropped.
    drop_own_alt_on_agree: bool = True

    def __post_init__(self) -> None:
        if self.policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}")

    def describe(self) -> dict[str, Any]:
        return {"tile": scene_prompt.prompt_id(self.tile_version) if self.tiles else None,
                "crop": scene_prompt.prompt_id(self.crop_version) if self.crops else None,
                "policy": self.policy, "drop_own_alt_on_agree": self.drop_own_alt_on_agree}


@dataclass
class FallbackResult:
    scene: SceneGraph
    issues: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    replies: list[dict[str, Any]] = field(default_factory=list)   # model output per region
    tiled: bool = False
    tiles_added: int = 0
    crops: int = 0
    codes_changed: int = 0


# ---------------------------------------------------------------- geometry


def tile_boxes(w: int, h: int, grid: int = TILE_GRID, overlap: float = TILE_OVERLAP) -> list[Box]:
    """A grid x grid cover of a w x h image; neighbouring tiles overlap by `overlap`
    of a tile's size. Row by row, top-left first."""
    def spans(n: int) -> list[tuple[int, int]]:
        t = n / (grid - overlap * (grid - 1))
        step = t * (1 - overlap)
        out = []
        for k in range(grid):
            a = round(k * step)
            b = n if k == grid - 1 else round(k * step + t)
            out.append((a, min(n, b)))
        return out
    return [(x0, y0, x1, y1) for (y0, y1) in spans(h) for (x0, x1) in spans(w)]


def tile_scale(w: int, h: int) -> float:
    """Enlarge (or shrink) a tile up to the scene prep's limits."""
    return min(LONG_EDGE / max(w, h), math.sqrt(MAX_PIXELS / (w * h)))


def crop_box(box: Box, w: int, h: int) -> Box:
    """The crop around a sign's box on the original (see the module docstring)."""
    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    cx0, cx1 = x0 - CROP_MARGIN["left"] * bw, x1 + CROP_MARGIN["right"] * bw
    cy0, cy1 = y0 - CROP_MARGIN["top"] * bh, y1 + CROP_MARGIN["bottom"] * bh

    def grow(a: float, b: float, n: int) -> tuple[float, float]:
        a, b = max(0.0, a), min(float(n), b)          # the margins are clipped to the image
        need = min(CROP_MIN_SHORT, n) - (b - a)
        if need > 0:                                   # too small: grow around the centre,
            a, b = a - need / 2, b + need / 2          # shifted to stay inside the image
            if a < 0:
                a, b = 0.0, b - a
            if b > n:
                a, b = a - (b - n), float(n)
        return max(0.0, a), min(float(n), b)

    cx0, cx1 = grow(cx0, cx1, w)               # each side at least CROP_MIN_SHORT (or the image)
    cy0, cy1 = grow(cy0, cy1, h)
    return (int(math.floor(cx0)), int(math.floor(cy0)), int(math.ceil(cx1)), int(math.ceil(cy1)))


def crop_scale(w: int, h: int) -> float:
    """Enlarge a crop to CROP_UPSCALE_SHORT on its short side; never past the long-edge limit."""
    s = max(1.0, CROP_UPSCALE_SHORT / min(w, h))
    return min(s, LONG_EDGE / max(w, h)) if max(w, h) * s > LONG_EDGE else s


def iou(a: Box, b: Box) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def centre_inside(a: Box, b: Box) -> bool:
    cx, cy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    return b[0] <= cx <= b[2] and b[1] <= cy <= b[3]


def same_region(a: Box, b: Box) -> bool:
    return iou(a, b) >= DEDUP_IOU or centre_inside(a, b) or centre_inside(b, a)


# ---------------------------------------------------------------- A1: dedup and ranks


def dedup(pass1: list[Box], found: list[tuple[Sign, Box]]) -> tuple[list[tuple[Sign, Box]], int]:
    """Tile signs that no pass-1 box and no kept tile sign already covers. `found` is
    in tile order; the more confident reading of a duplicate wins, then the earlier."""
    order = sorted(range(len(found)), key=lambda k: (_RANK[found[k][0].confidence], k))
    kept: list[int] = []
    for k in order:
        b = found[k][1]
        if any(same_region(b, p) for p in pass1) or any(same_region(b, found[j][1]) for j in kept):
            continue
        kept.append(k)
    kept.sort()
    return [found[k] for k in kept], len(found) - len(kept)


def place_ranks(pass1: list[Sign], tops: list[float | None], added: list[tuple[Sign, float]],
                width: int) -> list[Sign]:
    """Option B ("shift", owner, 2026-11-16). `tops` are the pass-1 signs' box tops on
    the original (None without a box); `added` are (sign, box top) on the original.

    Pass-1 signs form rank levels (tied ranks are one level). A level's top is the
    smallest box top among its signs; a level with no box takes the top of the level
    before it. An added sign goes in after the last level whose top is at or above
    its own; the pass-1 signs after it move down by one. Pass-1 order, ties and sides
    never change; signs without a rank are left as they are."""
    ranks = sorted({s.position.rank_top_down for s in pass1 if s.position.rank_top_down is not None})
    levels: list[dict[str, Any]] = []
    prev = -math.inf
    for r in ranks:
        ts = [t for s, t in zip(pass1, tops) if s.position.rank_top_down == r and t is not None]
        top = min(ts) if ts else prev
        levels.append({"top": top, "pass1": r})
        prev = top
    for k, (sign, top) in sorted(enumerate(added), key=lambda e: (e[1][1], e[0])):
        at = max((i + 1 for i, lv in enumerate(levels) if lv["top"] <= top), default=0)
        levels.insert(at, {"top": top, "added": k})
    final: dict[tuple[str, int], int] = {}
    added_before, prev = 0, 0
    for lv in levels:
        if "pass1" in lv:                  # moves down by the number of signs added above it
            prev = final[("p", lv["pass1"])] = lv["pass1"] + added_before
        else:                              # one below the level before it (1 at the top)
            added_before += 1
            prev = final[("a", lv["added"])] = prev + 1
    out = []
    for s in pass1:
        r = s.position.rank_top_down
        if r is None:
            out.append(s)
            continue
        out.append(s.model_copy(update={"position": s.position.model_copy(
            update={"rank_top_down": final[("p", r)]})}))
    for k, (sign, _) in enumerate(added):
        box = sign.position.box
        cx = (box[0] + box[2]) / 2 if box else None
        side = Side.unknown if cx is None else (Side.left if cx < width / 2 else Side.right)
        out.append(sign.model_copy(update={"position": sign.position.model_copy(
            update={"rank_top_down": final[("a", k)], "side": side})}))
    return out


# ---------------------------------------------------------------- A2: crop readings


@dataclass(frozen=True)
class CropReading:
    code: str                      # a catalog code or variant, or UNKNOWN
    confidence: Confidence
    value: float | None = None
    unit: str | None = None
    alt: AltReading | None = None
    raw_code: str | None = None    # the code as read, when it was not in the catalog


def parse_crop(data: Any, catalog: Catalog) -> CropReading:
    """A crop reply. An invalid code becomes UNKNOWN (raw kept); an invalid confidence
    is low; a value that is not a number is dropped."""
    if not isinstance(data, dict):
        return CropReading("UNKNOWN", Confidence.low)
    code, err = resolve_code(data.get("code"), catalog)
    raw = None
    if err:
        code, raw = "UNKNOWN", str(data.get("code"))
    try:
        conf = Confidence(data.get("confidence"))
    except ValueError:
        conf = Confidence.low
    v = data.get("value")
    value = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    unit = data.get("unit") if isinstance(data.get("unit"), str) and value is not None else None
    alt = None
    a = data.get("alt")
    if isinstance(a, dict):
        acode, aerr = resolve_code(a.get("code"), catalog)
        av = a.get("value")
        if not aerr and acode != "UNKNOWN":
            alt = AltReading(code=acode, value=float(av) if isinstance(av, (int, float))
                             and not isinstance(av, bool) else None)
    return CropReading(code, conf, value, unit, alt, raw)


def _agree(code_a: str, value_a: float | None, code_b: str, value_b: float | None,
           catalog: Catalog) -> bool:
    ra, rb = row_of(code_a, catalog), row_of(code_b, catalog)
    if ra is None or rb is None or ra != rb:
        return False
    return value_a is None or value_b is None or value_a == value_b


def own_alternatives(s: Sign, pass1_issues: list[str]) -> list[AltReading]:
    """The sign's alternatives that come from its own reply (the `alt` field), not from
    the re-run. The re-run's are the ones `verify.merge_rerun` reported as
    "<code>: the re-run read <alt>[ <value>]; kept as an alternative" (matched on the
    code, since sign ids are renumbered after the merge)."""
    def from_rerun(a: AltReading) -> bool:
        tail = (f"{s.code}: the re-run read {a.code}" + (f" {a.value}" if a.value is not None else "")
                + "; kept as an alternative")
        return any(i.split(" ", 1)[-1] == tail for i in pass1_issues)
    return [a for a in s.alternatives if not from_rerun(a)]


def _as_alt(s: Sign) -> AltReading:
    return AltReading(code=s.code, value=s.value, confidence=Confidence.low)


def _take_crop(s: Sign, c: CropReading, alts: list[AltReading]) -> Sign:
    return s.model_copy(update={"code": c.code, "value": c.value, "unit": c.unit,
                                "confidence": Confidence.low, "alternatives": alts})


def combine(s: Sign, c: CropReading, policy: str = "rules",
            catalog: Catalog | None = None) -> tuple[Sign, str]:
    """Combine a pass-1 sign with its crop reading; returns (sign, what happened).

    In every policy a crop that reads UNKNOWN changes nothing, and a crop that agrees
    with pass 1 (same catalog row, values not in conflict) raises the sign to medium.
    Otherwise:
    - "rules" (the proposal's rules):
      pass 1 UNKNOWN -> the crop's code, kept at low;
      the crop agrees with one of pass 1's alternatives -> swap: the crop's code first,
      pass 1's reading as an alternative, kept at low;
      any other disagreement -> pass 1's code stays and the crop's is added as an
      alternative; if the crop is high, the crop's code goes first instead;
    - "crop_always": the crop's code first, pass 1's reading as an alternative;
    - "crop_high": as crop_always when the crop is high, else the crop's code is added
      as an alternative;
    - "never": the crop's code is only ever added as an alternative.
    """
    catalog = catalog or load_catalog()
    if c.code == "UNKNOWN":
        return s, "crop read UNKNOWN; no change"
    if s.code != "UNKNOWN" and _agree(s.code, s.value, c.code, c.value, catalog):
        return s.model_copy(update={"confidence": Confidence.medium}), "crop agrees; raised to medium"
    crop_alt = AltReading(code=c.code, value=c.value, confidence=c.confidence)
    keep_alts = [a for a in s.alternatives]
    if policy == "never":
        return s.model_copy(update={"alternatives": [*keep_alts, crop_alt]}), \
            f"crop read {c.code}; added as an alternative"
    if policy == "crop_always" or (policy == "crop_high" and c.confidence == Confidence.high):
        prior = [] if s.code == "UNKNOWN" else [_as_alt(s)]
        return _take_crop(s, c, [*prior, *keep_alts]), f"crop read {c.code}; replaces {s.code}"
    if policy == "crop_high":
        return s.model_copy(update={"alternatives": [*keep_alts, crop_alt]}), \
            f"crop read {c.code} ({c.confidence.value}); added as an alternative"
    # "rules"
    if s.code == "UNKNOWN":
        return _take_crop(s, c, keep_alts), f"crop read {c.code}; replaces UNKNOWN"
    for i, a in enumerate(keep_alts):
        if _agree(a.code, a.value, c.code, c.value, catalog):
            rest = keep_alts[:i] + keep_alts[i + 1:]
            return _take_crop(s, c, [_as_alt(s), *rest]), \
                f"crop agrees with the alternative {a.code}; swapped with {s.code}"
    if c.confidence == Confidence.high:
        return _take_crop(s, c, [_as_alt(s), *keep_alts]), f"crop read {c.code} (high); replaces {s.code}"
    return s.model_copy(update={"alternatives": [*keep_alts, crop_alt]}), \
        f"crop read {c.code}; added as an alternative"


# ---------------------------------------------------------------- images


def original_image(data: bytes):
    """The original image, EXIF-oriented, RGB (the frame pass-1 boxes map onto)."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def region_block(im, box: Box, scale: float) -> dict[str, Any]:
    import base64

    from PIL import Image

    part = im.crop(box)
    w, h = part.size
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    if (nw, nh) != (w, h):
        part = part.resize((nw, nh), Image.LANCZOS)
    buf = io.BytesIO()
    part.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode("ascii")}}


# ---------------------------------------------------------------- the calls


Lookup = Callable[[str, Box], "str | None"]


def _region_reply(kind: str, box: Box, im, scale: float, version: str, *, img: PreparedImage,
                  model: str, client, cache: SceneCache, use_cache: bool, replay: Lookup | None,
                  res: FallbackResult) -> str | None:
    """The raw reply for one tile or crop: from the replay, the cache, or a call.

    A reply that is not one JSON object gets one retry that sends only the error (D4,
    as the scene call). Each failed attempt is kept with its raw text (in `res.replies`,
    marked failed, and quoted in `res.issues`). Only a usable reply is cached, so a
    region whose retry fails too is called again next time."""
    pid = scene_prompt.prompt_id(version)
    effort = scene_prompt.effort_for(model, version)
    where = f"{kind} {list(box)}"
    if replay is not None:
        text = replay(kind, box)
        if text is None:
            res.issues.append(f"{where}: no reply to replay; skipped")
        return text
    if use_cache and (rec := cache.get_region(img.sha256, model, effort, pid, box)) is not None:
        text = rec.replies[-1]["raw_text"]
        res.replies.append({"kind": kind, "box": list(box), "prompt_id": pid, "raw_text": text,
                            "cost_usd": 0.0, "cache_hit": True})
        return text
    system = scene_prompt.system_prompt(version)
    user = scene_prompt.user_content(region_block(im, box, scale), version)
    max_tokens = scene_prompt.config(version)["max_tokens"]
    stored: list[dict[str, Any]] = []          # what goes to the cache record

    def call(extra=None):
        return client.json_reply(system=system, user=user, max_tokens=max_tokens, effort=effort,
                                 purpose=f"scene {kind}" + (" retry" if extra else ""),
                                 extra_messages=extra)

    def failed(e: Exception, attempt: int) -> None:
        raw = getattr(e, "raw_text", "") or ""
        cost = getattr(e, "cost_usd", 0.0)
        res.cost_usd += cost
        res.replies.append({"kind": kind, "box": list(box), "prompt_id": pid, "raw_text": raw,
                            "cost_usd": cost, "failed": True, "attempt": attempt, "error": str(e)})
        stored.append({"pass": f"{kind} failed", "raw_text": raw, "stop_reason": "end_turn",
                       "usage": getattr(client, "last_usage", None) or {}, "cost_usd": cost,
                       "request_id": None})

    attempt = 1
    try:
        reply = call()
    except (LLMRefusal, LLMTruncated) as e:
        res.cost_usd += getattr(e, "cost_usd", 0.0)
        res.issues.append(f"{where}: call failed ({type(e).__name__}); skipped")
        return None
    except LLMBadJSON as e:
        failed(e, 1)
        res.issues.append(f"{where}: reply not JSON ({e}); retried. Reply was: "
                          f"{(getattr(e, 'raw_text', '') or '')[:500]!r}")
        attempt = 2
        try:
            reply = call(retry_messages([str(e)]))
        except LLMBadJSON as e2:
            failed(e2, 2)
            res.issues.append(f"{where}: call failed (LLMBadJSON after the retry); skipped. Reply was: "
                              f"{(getattr(e2, 'raw_text', '') or '')[:500]!r}")
            return None
        except (LLMRefusal, LLMTruncated) as e2:
            res.cost_usd += getattr(e2, "cost_usd", 0.0)
            res.issues.append(f"{where}: call failed ({type(e2).__name__} on the retry); skipped")
            return None
    res.cost_usd += reply.cost_usd
    stored.append({"pass": kind if attempt == 1 else f"{kind} retry", "raw_text": reply.raw_text,
                   "stop_reason": "end_turn", "usage": reply.usage, "cost_usd": reply.cost_usd,
                   "request_id": reply.request_id})
    cache.put_region(RegionRecord(img.sha256, model, effort, pid, box, replies=stored))
    res.replies.append({"kind": kind, "box": list(box), "prompt_id": pid, "raw_text": reply.raw_text,
                        "cost_usd": reply.cost_usd, "usage": reply.usage, "request_id": reply.request_id,
                        "attempt": attempt})
    return reply.raw_text


def _box_on_original(s: Sign, img: PreparedImage) -> Box | None:
    b = s.position.box
    if b is None:
        return None
    x0, y0, x1, y1 = img.to_original(b)
    w, h = img.original_size
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def needs_tiles(scene: SceneGraph) -> bool:
    return len(scene.signs) >= DENSE_MIN_SIGNS


def needs_crop(s: Sign) -> bool:
    return s.code == "UNKNOWN" or s.confidence == Confidence.low


def run_fallback(scene: SceneGraph, image_bytes: bytes, img: PreparedImage, *, model: str,
                 client=None, cfg: FallbackConfig = FallbackConfig(),
                 cache: SceneCache | None = None, use_cache: bool = True,
                 replay: Lookup | None = None, catalog: Catalog | None = None,
                 pass1_issues: list[str] | None = None) -> FallbackResult:
    """A1 then A2 on a pass-1 scene (see the module docstring). With `replay`, replies
    come from it and no call is made. `pass1_issues` (pass 1's verification messages)
    tell pass 1's own alternatives from the re-run's (T4)."""
    catalog = catalog or load_catalog()
    cache = cache if cache is not None else SceneCache()
    res = FallbackResult(scene=scene)
    im = original_image(image_bytes)
    W, H = img.original_size
    signs = list(scene.signs)
    added_ids: set[str] = set()
    common = dict(img=img, model=model, client=client, cache=cache, use_cache=use_cache,
                  replay=replay, res=res)

    # A1: region pass
    if cfg.tiles and needs_tiles(scene):
        res.tiled = True
        found: list[tuple[Sign, Box]] = []
        for t, tb in enumerate(tile_boxes(W, H)):
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            sc = tile_scale(tw, th)
            text = _region_reply("tile", tb, im, sc, cfg.tile_version, **common)
            if text is None:
                continue
            try:
                w = to_scene(parse_json_reply(text), scene.scene_id, final=True, catalog=catalog)
            except LLMBadJSON as e:
                res.issues.append(f"tile {list(tb)}: reply not usable ({e}); skipped")
                continue
            if w.scene is None:
                res.issues.append(f"tile {list(tb)}: reply not usable; skipped")
                continue
            for k, s in enumerate(w.scene.signs, 1):
                b = s.position.box
                if b is None:
                    res.issues.append(f"tile {t + 1} sign {k} {s.code}: no box; left out")
                    continue
                ob = (max(0, round(tb[0] + b[0] / sc)), max(0, round(tb[1] + b[1] / sc)),
                      min(W, round(tb[0] + b[2] / sc)), min(H, round(tb[1] + b[3] / sc)))
                if ob[2] <= ob[0] or ob[3] <= ob[1]:
                    continue
                found.append((s.model_copy(update={"id": f"t{len(found) + 1}"}), ob))
        p1 = [b for s in signs if (b := _box_on_original(s, img)) is not None]
        kept, dropped = dedup(p1, found)
        added = []
        for s, ob in kept:
            sent = tuple(int(round(v * img.scale)) for v in ob)
            pos = s.position.model_copy(update={"rank_top_down": None, "side": Side.unknown, "box": sent})
            s = s.model_copy(update={"confidence": Confidence.low, "position": pos})
            added.append((s, float(ob[1])))
            added_ids.add(s.id)
            res.issues.append(f"{s.id} {s.code}: added by the region pass at low")
        if dropped:
            res.issues.append(f"region pass: {dropped} tile sign(s) already listed; dropped")
        if added:
            tops = [None if (b := _box_on_original(s, img)) is None else float(b[1]) for s in signs]
            signs = place_ranks(signs, tops, added, W)
        res.tiles_added = len(added)

    # A2: box crops
    changed: set[str] = set()
    if cfg.crops:
        out = []
        for s in signs:
            if not needs_crop(s):
                out.append(s)
                continue
            ob = _box_on_original(s, img)
            if ob is None:
                res.issues.append(f"{s.id} {s.code}: low or UNKNOWN but no box; not cropped")
                out.append(s)
                continue
            cb = crop_box(ob, W, H)
            res.crops += 1
            text = _region_reply("crop", cb, im, crop_scale(cb[2] - cb[0], cb[3] - cb[1]),
                                 cfg.crop_version, **common)
            if text is None:
                out.append(s)
                continue
            try:
                reading = parse_crop(parse_json_reply(text), catalog)
            except LLMBadJSON as e:
                res.issues.append(f"{s.id} {s.code}: crop reply not usable ({e}); no change")
                out.append(s)
                continue
            new, what = combine(s, reading, cfg.policy, catalog)
            if (cfg.drop_own_alt_on_agree and what.startswith("crop agrees") and s.id not in added_ids
                    and (own := own_alternatives(s, pass1_issues or []))):
                new = new.model_copy(update={"alternatives": [a for a in new.alternatives if a not in own]})
                what += "; pass 1's own alternative " + ", ".join(a.code for a in own) + " dropped"
            if new.code != s.code:
                res.codes_changed += 1
            if new != s:
                changed.add(s.id)
            res.issues.append(f"{s.id} {s.code}: {what}")
            out.append(new)
        signs = out

    if not added_ids and not changed:
        res.scene = scene.model_copy(update={"signs": signs})
        return res
    final, more = verify(scene.model_copy(update={"signs": signs}), catalog)
    touched = added_ids | changed
    res.issues += [m for m in more if m.split(" ", 1)[0] in touched or "renumbered" in m]
    res.scene = final
    return res
