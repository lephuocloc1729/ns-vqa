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
# Kept apart from RUN_SPECIFIC because the phase-4 record lists RUN_SPECIFIC verbatim.
POST_FREEZE_SWITCHES = {"answer_fallback": True}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def live(perception_model: str | None = None) -> dict[str, Any]:
    from eval import judge
    from vqa.answer import fallback as afb
    from vqa.answer import prompt as wp
    from vqa.parsing import prompt as pp
    from vqa.perception import fallback as sfb
    from vqa.perception import prompt as sp
    from vqa.pipeline import PipelineConfig

    c = PipelineConfig(**({"perception_model": perception_model} if perception_model else {}))
    pc = {k: v for k, v in dataclasses.asdict(c).items() if k not in RUN_SPECIFIC and k not in POST_FREEZE_SWITCHES}
    fc = sfb.FallbackConfig()
    pm = c.perception_model
    parser_system = pp.system_prompt(c.parser_version)

    def scene(version: str) -> dict[str, Any]:
        cfg = sp.config(version)
        return {"id": sp.prompt_id(version), "sha256": sp.prompt_hash(version),
                "model": pm, "effort": sp.effort_for(pm, version), "max_tokens": cfg.get("max_tokens")}

    wcfg, fcfg, jcfg = wp.config(c.writer_version), afb.config(c.answer_fallback_version), judge.config()
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
    rec = load(path)
    return diff(json.loads(json.dumps(rec)), json.loads(json.dumps(live(perception_model), default=str)))


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
    a = ap.parse_args()
    if a.cmd == "show":
        print(json.dumps(live(), indent=2, default=str))
    elif a.cmd == "check":
        d = check()
        print("matches the freeze record" if not d else "\n".join(d))
        raise SystemExit(1 if d else 0)
    else:
        if FROZEN.exists():
            raise SystemExit(f"{FROZEN.name} exists; the freeze is written once")
        FROZEN.write_text(json.dumps(live(), indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        print(f"freeze record -> {FROZEN}")


if __name__ == "__main__":
    main()
