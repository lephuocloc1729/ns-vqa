"""Owner, 2026-11-18 (phase 4.8, option 1, as for phase 4.6 in 6b014df): phase 4.8 adds engine files, so
the phase-4.7 record's engine-code hash no longer matches the working tree. Tests that need the
phase-4.7 record to match check its hash against the files at the freeze commit, read from git, then
use a copy of the record whose engine_code is the working tree's, so every other field is still
checked against the tree. The run-time guards in eval/freeze.py and eval/e2e_private.py are unchanged:
a run from this tree with the real record is refused."""

from __future__ import annotations

import functools
import io
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path

import eval.freeze as fz

PHASE47_FREEZE_COMMIT = "4ad9137"


@functools.lru_cache(maxsize=None)
def code_hash_at(commit: str) -> str:
    blob = subprocess.run(["git", "archive", commit, "vqa", "kb"], cwd=fz.ROOT, capture_output=True,
                          check=True).stdout
    tmp = Path(tempfile.mkdtemp(prefix=f"code_at_{commit}_"))
    with tarfile.open(fileobj=io.BytesIO(blob)) as t:
        t.extractall(tmp, filter="data")
    return json.dumps(fz.code_hash(tmp), sort_keys=True)


def phase47_record_for_this_tree() -> dict:
    """The phase-4.7 record, after checking its engine-code hash against the freeze commit, with
    engine_code set to the working tree's."""
    rec = fz.load(fz.FROZEN_PHASE47)
    assert json.dumps(rec["engine_code"], sort_keys=True) == code_hash_at(PHASE47_FREEZE_COMMIT)
    return {**rec, "engine_code": fz.code_hash()}


def phase47_record_file(folder: Path) -> Path:
    """That record written as `frozen_phase47.json` in `folder` (the name the runners record)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / "frozen_phase47.json"
    p.write_text(json.dumps(phase47_record_for_this_tree()), encoding="utf-8")
    return p
