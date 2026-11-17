"""Exercise the owner's judged-dev command through argument parsing, without starting a run."""
import sys

import pytest

from eval import e2e_dev
from vqa.perception.fallback import config_for
from vqa.pipeline import PipelineConfig


@pytest.mark.parametrize("flags, expected", [
    ([], None),
    (["--candidate"], e2e_dev.CANDIDATE),
    (["--candidate", "--scene-version", "v6", "--parser-version", "v12",
      "--reading-policy", "higher_confidence"],
     {"scene_version": "v6", "parser_version": "v12", "guide_reading": True,
      "reading_policy": "higher_confidence"}),
])
def test_judged_dev_cli(monkeypatch, flags, expected):
    calls = []
    monkeypatch.setattr(sys, "argv", ["e2e_dev.py", "run", "--label", "check", "--max-spend", "1.05", *flags])
    monkeypatch.setattr(e2e_dev, "run_dev", lambda label, cap, candidate: calls.append((label, cap, candidate)))
    e2e_dev.main()
    assert calls == [("check", 1.05, expected)]
    if expected and expected["scene_version"] == "v6":
        config = PipelineConfig(answer_fallback=False, **expected)
        fb = config_for(config.scene_version)
        assert (fb.tile_version, fb.crop_version) == ("v6-tile", "v6-crop")
        ids = e2e_dev.candidate_prompt_ids(expected)
        for key, prefix in {"scene": "scene/v6@", "scene_tile": "scene/v6-tile@",
                            "scene_crop": "scene/v6-crop@", "parser": "parser/v12@"}.items():
            assert ids[key].startswith(prefix)
