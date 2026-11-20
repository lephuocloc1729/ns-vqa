"""The phase-4 freeze (docs/plans/phase-4.md, procedure step 5; owner, 2026-11-16).

`live()` reads the configuration the pipeline would run with today, from the code:
- the PipelineConfig defaults (without the run-specific fields);
- every prompt id with its full sha256: scene v4, v4-tile, v4-crop, parser v6,
  answer v3, answer_fallback v2, judge v1;
- the scene fallback's CHOSEN_POLICY and drop_own_alt_on_agree;
- each stage's model, effort and max_tokens.

`eval/frozen_phase4.json` (committed) is the record of it. `check()` lists every
difference between the two; the holdout run refuses to start unless there is none.

    .venv/bin/python eval/freeze.py show        # the live configuration
    .venv/bin/python eval/freeze.py check       # live vs the record
    .venv/bin/python eval/freeze.py write       # write the record (refuses to overwrite)
    .venv/bin/python eval/freeze.py check --profile phase45   # the phase-4.5 record (B5)
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FROZEN = ROOT / "eval" / "frozen_phase4.json"
# PipelineConfig fields that differ per run by design (the holdout uses its own
# temporary cache, fresh perception and its own spend limit).
RUN_SPECIFIC = ("cache_dir", "cache_only", "max_spend")
# Switches added after the phase-4 freeze, left out of the comparison the same way. Their
# defaults are the frozen behaviour. `answer_fallback` (phase 4.5): off, a question the
# rules don't decide gets no fallback call; decided answers are the same either way.
# `guide_reading` (phase 4.5 B6): off, no guide-board call, the frozen behaviour.
# `reading_policy` (phase 4.6, D1): "all", disagreeing readings give `uncertain`, the frozen
# behaviour of both records; "higher_confidence" is policy A.
# Kept apart from RUN_SPECIFIC because the phase-4 record lists RUN_SPECIFIC verbatim.
POST_FREEZE_SWITCHES = {"answer_fallback": True, "guide_reading": False, "reading_policy": "all"}

# Phase 4.5 (owner, 2026-11-17, B5): freeze profiles. A profile is the PipelineConfig fields that
# differ from today's defaults (which stay the phase-4 configuration, so its record and runs
# are untouched). A record names its profile ("phase4" when it names none); the runners build
# their pipeline from the profile of the record they check.
FROZEN_PHASE45 = ROOT / "eval" / "frozen_phase45.json"
# Phase 4.6 (owner, 2026-11-17, D4): the round-2 system, for the final2 validation run and the
# private test: scene v5 + guide reading, parser v11, reading policy A.
FROZEN_PHASE46 = ROOT / "eval" / "frozen_phase46.json"
# Phase 4.7 (owner, 2026-11-18): scene v5 + guide reading, parser v14, reading policy A, and the scene v6
# field switch (kb/v6_fields_47.yaml: signals off), for the private test.
FROZEN_PHASE47 = ROOT / "eval" / "frozen_phase47.json"
# Phase 4.8 (owner, 2026-11-18): scene v5 + guide reading (perception unchanged), parser v16, reading
# policy A, the v6 field switch (signals off) and the phase-4.8 engine switches (kb/switches_48.yaml:
# several_signs on, confusable_pairs off), for the private test.
FROZEN_PHASE48 = ROOT / "eval" / "frozen_phase48.json"
FROZEN_PHASE49 = ROOT / "eval" / "frozen_phase49.json"
PROFILES: dict[str, dict[str, Any]] = {
    "phase4": {},
    "phase45": {"scene_version": "v5", "parser_version": "v9", "guide_reading": True},
    "phase46": {"scene_version": "v5", "parser_version": "v11", "guide_reading": True,
                "reading_policy": "higher_confidence"},
    "phase47": {"scene_version": "v5", "parser_version": "v14", "guide_reading": True,
                "reading_policy": "higher_confidence"},
    "phase48": {"scene_version": "v5", "parser_version": "v16", "guide_reading": True,
                "reading_policy": "higher_confidence"},
}
PROFILES["phase49"] = {**PROFILES["phase48"], "parser_version": "v17"}
RECORDS = {"phase4": FROZEN, "phase45": FROZEN_PHASE45, "phase46": FROZEN_PHASE46, "phase47": FROZEN_PHASE47,
           "phase48": FROZEN_PHASE48, "phase49": FROZEN_PHASE49}
# Left out of a profile's comparison: phase 4 leaves out both post-freeze switches (their
# defaults are its behaviour); phase 4.5 freezes guide_reading (on) and still leaves out
# answer_fallback, which each runner sets (validation: off; private: the default, on).
EXCLUDED_SWITCHES = {"phase4": tuple(POST_FREEZE_SWITCHES), "phase45": ("answer_fallback",),
                     "phase46": ("answer_fallback",), "phase47": ("answer_fallback",),
                     "phase48": ("answer_fallback",)}
# Switches added after a record was written, left out of its comparison without changing the
# record's own `excluded_switches` list. Their defaults are that record's behaviour.
LATER_SWITCHES = {"phase4": (), "phase45": ("reading_policy",), "phase46": (), "phase47": (), "phase48": ()}
WHAT = {"phase45": "phase 4.5, B5: the frozen configuration for the final validation run and the private test",
        "phase46": "phase 4.6: the frozen configuration for the final2 validation run and the private test",
        "phase47": "phase 4.7: the frozen configuration for the private test (scene v5, parser v14, signals off)",
        "phase48": "phase 4.8: the frozen configuration for the private test (scene v5, parser v16, signals off, "
                   "several_signs on, confusable_pairs off)"}
# Phase 4.6: from this record on, the rule engine's code and knowledge base are frozen too (the
# prompts alone don't pin what the engine decides). Hashed: every .py under vqa/, and kb/.
CODE_HASHED_FROM = {"phase46", "phase47", "phase48"}
# Phase 4.7: the scene v6 fields the engine switches off (kb/v6_fields_47.yaml), named in the record
# (the file is also inside the engine-code hash).
V6_SWITCH_FROM = {"phase47", "phase48"}
# Phase 4.8: the engine switches (kb/switches_48.yaml), named in the record (the file is also hashed).
SWITCHES48_FROM = {"phase48"}


# Owner, 2026-11-18: v17 accepted with the measured dev guardrail shortfall.
EXCLUDED_SWITCHES["phase49"] = ("answer_fallback",)
LATER_SWITCHES["phase49"] = ()
WHAT["phase49"] = "phase 4.9: owner-approved v17 configuration; dev guardrail exception recorded in docs/status.md"
CODE_HASHED_FROM.add("phase49")
V6_SWITCH_FROM.add("phase49")
SWITCHES48_FROM.add("phase49")

# docs/plans/rerun-removal.md (owner, 2026-11-19): `scene_rerun` came after every record so far.
# Its default (True) is their behaviour, so it is left out of their comparison.
for _p in LATER_SWITCHES:
    LATER_SWITCHES[_p] = (*LATER_SWITCHES[_p], "scene_rerun")

# docs/plans/rerun-removal.md, R5 (owner-approved plan; R3 applied 2026-11-19 on the paired holdout
# check aa10b2294ae7): phase49 without the low-confidence scene re-run. Code hashed at the parallel
# calls (a16d32c) and the switch. Not for the private test: the benchmark stays phase49's one run.
FROZEN_PHASE50 = ROOT / "eval" / "frozen_phase50.json"
PROFILES["phase50"] = {**PROFILES["phase49"], "scene_rerun": False}
RECORDS["phase50"] = FROZEN_PHASE50
EXCLUDED_SWITCHES["phase50"] = ("answer_fallback",)
LATER_SWITCHES["phase50"] = ()
WHAT["phase50"] = ("phase 5.0: phase49 without the scene re-run (docs/plans/rerun-removal.md), with the parallel "
                   "API calls; not for the private test")
CODE_HASHED_FROM.add("phase50")
V6_SWITCH_FROM.add("phase50")
SWITCHES48_FROM.add("phase50")

# Owner request, 2026-11-20: phase50 with parser v18 and the rule and engine fixes of 65bbfbb
# (kb/rules/fixes50.pl and others). v18 gate run 20261120-140742: 80.9% (38/47), the same wrong rows as
# v17, regressed_types_without_design empty. Not yet accepted by the private runner (PRIVATE_PROFILES).
FROZEN_PHASE51 = ROOT / "eval" / "frozen_phase51.json"
PROFILES["phase51"] = {**PROFILES["phase50"], "parser_version": "v18"}
RECORDS["phase51"] = FROZEN_PHASE51
EXCLUDED_SWITCHES["phase51"] = ("answer_fallback",)
LATER_SWITCHES["phase51"] = ()
WHAT["phase51"] = ("phase 5.1: phase50 (no scene re-run, parallel calls) with parser v18 and the rule and "
                   "engine fixes of 65bbfbb")
CODE_HASHED_FROM.add("phase51")
V6_SWITCH_FROM.add("phase51")
SWITCHES48_FROM.add("phase51")

def code_hash(root: Path = ROOT) -> dict[str, Any]:
    files = sorted([*(root / "vqa").rglob("*.py"), *(root / "kb").rglob("*.pl"), *(root / "kb").rglob("*.yaml")])
    files = [f for f in files if "__pycache__" not in f.parts]
    h = hashlib.sha256()
    for f in files:
        h.update(str(f.relative_to(root)).encode("utf-8") + b"\0" + f.read_bytes() + b"\0")
    return {"files": len(files), "sha256": h.hexdigest(), "covers": ["vqa/**/*.py", "kb/**/*.pl", "kb/**/*.yaml"]}


def profile_of(record: dict[str, Any]) -> str:
    return record.get("profile", "phase4")


def pipeline_config(profile: str = "phase4", perception_model: str | None = None, **run: Any):
    """The PipelineConfig a profile runs with, plus run-specific fields (cache_dir, ...)."""
    from vqa.pipeline import PipelineConfig
    if profile not in PROFILES:
        raise SystemExit(f"unknown freeze profile {profile!r}; one of {sorted(PROFILES)}")
    kw = {**PROFILES[profile], **({"perception_model": perception_model} if perception_model else {}), **run}
    return PipelineConfig(**kw)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def live(perception_model: str | None = None, profile: str = "phase4") -> dict[str, Any]:
    from eval import judge
    from vqa.answer import fallback as afb
    from vqa.answer import prompt as wp
    from vqa.parsing import prompt as pp
    from vqa.perception import fallback as sfb
    from vqa.perception import guide
    from vqa.perception import prompt as sp

    c = pipeline_config(profile, perception_model)
    skip = EXCLUDED_SWITCHES[profile]
    pc = {k: v for k, v in dataclasses.asdict(c).items()
          if k not in RUN_SPECIFIC and k not in skip and k not in LATER_SWITCHES.get(profile, ())}
    fc = sfb.config_for(c.scene_version)
    pm = c.perception_model
    parser_system = pp.system_prompt(c.parser_version)

    def scene(version: str) -> dict[str, Any]:
        cfg = sp.config(version)
        return {"id": sp.prompt_id(version), "sha256": sp.prompt_hash(version),
                "model": pm, "effort": sp.effort_for(pm, version), "max_tokens": cfg.get("max_tokens")}

    wcfg, fcfg, jcfg = wp.config(c.writer_version), afb.config(c.answer_fallback_version), judge.config()
    out = _live_body(c, pc, fc, sfb, sp, pp, wp, afb, judge, scene, parser_system, wcfg, fcfg, jcfg)
    if profile == "phase4":
        return out
    gcfg = guide.config()
    out = {"what": WHAT[profile],
           "profile": profile, **{k: v for k, v in out.items() if k != "what"}}
    out["excluded_switches"] = list(skip)
    out["prompts"]["guide"] = {"id": guide.prompt_id(), "sha256": guide.prompt_hash(), "model": c.perception_model,
                               "effort": guide.effort_for(c.perception_model), "max_tokens": gcfg.get("max_tokens"),
                               "on": c.guide_reading}
    if profile in CODE_HASHED_FROM:
        out["engine_code"] = code_hash()
    if profile in V6_SWITCH_FROM:
        from vqa.reasoning.engine import v6_fields_off_from_kb
        out["v6_fields_off"] = list(v6_fields_off_from_kb())
    if profile in SWITCHES48_FROM:
        from vqa.reasoning.engine import switches_from_kb
        out["engine_switches"] = dict(sorted(switches_from_kb().items()))
    return out


def _live_body(c, pc, fc, sfb, sp, pp, wp, afb, judge, scene, parser_system, wcfg, fcfg, jcfg) -> dict[str, Any]:
    return {
        "what": "phase 4, procedure step 5: the frozen configuration for the one public_holdout run",
        "pipeline_config": pc,
        "run_specific_fields": list(RUN_SPECIFIC),
        "scene_fallback": {"policy": fc.policy, "chosen_policy": sfb.CHOSEN_POLICY,
                           "drop_own_alt_on_agree": fc.drop_own_alt_on_agree,
                           "tiles": fc.tiles, "crops": fc.crops, "describe": fc.describe()},
        "prompts": {
            "scene": scene(c.scene_version),
            "scene_tile": scene(fc.tile_version),
            "scene_crop": scene(fc.crop_version),
            "parser": {"id": f"parser/{c.parser_version}@{_sha(parser_system)[:12]}",
                       "sha256": _sha(parser_system), "model": c.parser_model, "effort": c.parser_effort},
            "answer": {"id": wp.prompt_id(c.writer_version), "sha256": wp.prompt_hash(c.writer_version),
                       "model": wcfg.get("model"), "effort": wcfg.get("effort"),
                       "max_tokens": wcfg.get("max_tokens")},
            "answer_fallback": {"id": afb.prompt_id(c.answer_fallback_version),
                                "sha256": afb.prompt_hash(c.answer_fallback_version),
                                "model": fcfg.get("model"), "effort": fcfg.get("effort"),
                                "max_tokens": fcfg.get("max_tokens"),
                                "output_schema": fcfg.get("output_schema")},
            "judge": {"id": judge.prompt_id(), "sha256": judge.prompt_hash(), "model": jcfg.get("model"),
                      "effort": jcfg.get("effort"), "max_tokens": jcfg.get("max_tokens")},
        },
    }


def load(path: Path = FROZEN) -> dict[str, Any]:
    if not Path(path).exists():
        raise SystemExit(f"no freeze record at {path}: the configuration is not frozen")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def diff(a: Any, b: Any, where: str = "") -> list[str]:
    """Every path where the two JSON values differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{where}{k}: only in {'the record' if k in a else 'the live configuration'}")
            else:
                out += diff(a[k], b[k], f"{where}{k}.")
        return out
    return [] if a == b else [f"{where.rstrip('.')}: record {a!r}, live {b!r}"]


def check(path: Path = FROZEN, perception_model: str | None = None) -> list[str]:
    """Every difference between a record and the live configuration of the record's profile."""
    rec = load(path)
    return diff(json.loads(json.dumps(rec)),
                json.loads(json.dumps(live(perception_model, profile_of(rec)), default=str)))


def git_state(root: Path = ROOT) -> dict[str, Any]:
    """The commit and whether the working tree is clean (gitignored files don't count)."""
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
                            check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True,
                           check=True).stdout.splitlines()
    return {"commit": commit, "clean": not dirty, "dirty": dirty}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["show", "check", "write"])
    ap.add_argument("--profile", choices=sorted(PROFILES), default="phase4")
    a = ap.parse_args()
    path = RECORDS[a.profile]
    if a.cmd == "show":
        print(json.dumps(live(profile=a.profile), indent=2, default=str))
    elif a.cmd == "check":
        d = check(path)
        print("matches the freeze record" if not d else "\n".join(d))
        raise SystemExit(1 if d else 0)
    else:
        write(path, a.profile)


def write(path: Path, profile: str) -> Path:
    if Path(path).exists():
        raise SystemExit(f"{Path(path).name} exists; the freeze is written once")
    Path(path).write_text(json.dumps(live(profile=profile), indent=2, ensure_ascii=False, default=str) + "\n",
                          encoding="utf-8")
    print(f"freeze record -> {path}")
    return Path(path)


if __name__ == "__main__":
    main()
