"""tools/naturalized_layer.py: the naturalized dataset as an annotation layer over the VLSP release.
Hand-made fake dataset and fake VLSP release in tmp_path; no dataset file is read."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.naturalized_layer as nl

SECRET = "secret-gold-answer"
QS = {"train": [{"id": "fake_tr_q1", "image_id": "fake_tr_img1", "question": "Biển gì?", "answer": f"Cấm {SECRET}"}],
      "public_test": [{"id": "fake_pu_q1", "image_id": "fake_pu_img1", "question": "Đúng không?", "answer": "Đúng"}]}


def _write(p: Path, data: bytes | str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return p


@pytest.fixture
def world(tmp_path):
    """A naturalized dataset, and a VLSP release holding its images and law_db in another layout."""
    nat, vlsp = tmp_path / "natural", tmp_path / "vlsp"
    for name in ("README.md", "manifest.json", "review.json", "provenance.json"):
        _write(nat / name, f'{{"file": "{name}"}}')
    _write(nat / ".DS_Store", b"junk")
    for split, (folder, js, images) in nl.SPLITS.items():
        _write(nat / "dataset" / folder / js, json.dumps(QS[split], ensure_ascii=False))
        img = f"image bytes of {split}".encode()
        _write(nat / "dataset" / folder / images / f"{QS[split][0]['image_id']}.jpg", img)
        _write(vlsp / "somewhere" / split / f"{QS[split][0]['image_id']}.jpg", img)        # VLSP's own layout
    _write(nat / "dataset/law_db/vlsp2025_law.json", '{"law": 1}')
    _write(nat / "dataset/law_db/images.fld/image001.png", b"figure")
    _write(vlsp / "dataset/law_db/vlsp2025_law.json", '{"law": 1}')
    _write(vlsp / "dataset/law_db/images.fld/image001.png", b"figure")
    _write(vlsp / "decoy/fake_tr_img1.jpg", b"a different photo with the same name")              # never picked
    return tmp_path, nat, vlsp


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): nl.sha256(p) for p in nl._files(root)}


def test_a_round_trip_rebuilds_the_dataset_exactly(world, capsys):
    tmp, nat, vlsp = world
    nl.export(nat, tmp / "layer", repo=tmp / "repo")
    nl.build(tmp / "layer", vlsp, tmp / "rebuilt")
    want = {k: v for k, v in _tree(nat).items() if k != nl.PROVENANCE}
    assert _tree(tmp / "rebuilt") == want
    printed = capsys.readouterr().out
    assert SECRET not in printed and "fake_tr_img1" not in printed and "Biển" not in printed


def test_the_layer_holds_the_authors_text_only(world):
    tmp, nat, _ = world
    nl.export(nat, tmp / "layer", repo=tmp / "repo")
    files = set(_tree(tmp / "layer"))
    assert not any(f.endswith((".jpg", ".png")) or f.endswith("vlsp2025_law.json") for f in files)
    assert nl.PROVENANCE not in files and nl.LAYER_FILE in files
    rec = json.loads((tmp / "layer" / nl.LAYER_FILE).read_text())
    assert len(rec["vlsp_files"]) == 4 and "dataset/law_db/vlsp2025_law.json" in rec["vlsp_files"]


def test_provenance_only_on_request(world):
    tmp, nat, vlsp = world
    nl.export(nat, tmp / "layer", repo=tmp / "repo", with_provenance=True)
    nl.build(tmp / "layer", vlsp, tmp / "rebuilt")
    assert _tree(tmp / "rebuilt") == _tree(nat)


def test_a_layer_of_the_train_split_only(world):
    tmp, nat, vlsp = world
    nl.export(nat, tmp / "layer", repo=tmp / "repo", splits=("train",))
    rec = json.loads((tmp / "layer" / nl.LAYER_FILE).read_text())
    assert rec["splits"] == ["train"] and not any("public_test" in f for f in [*rec["text_files"], *rec["vlsp_files"]])
    nl.build(tmp / "layer", vlsp, tmp / "rebuilt")
    assert not (tmp / "rebuilt" / "dataset" / nl.SPLITS["public_test"][0]).exists()


def test_the_private_test_is_never_part_of_the_layer(world):
    tmp, nat, _ = world
    assert set(nl.SPLITS) == {"train", "public_test"}
    with pytest.raises(SystemExit, match="unknown split"):
        nl.export(nat, tmp / "layer", repo=tmp / "repo", splits=("private_test",))


def test_a_missing_or_changed_vlsp_file_is_refused_with_counts_only(world):
    tmp, nat, vlsp = world
    nl.export(nat, tmp / "layer", repo=tmp / "repo")
    (vlsp / "somewhere/public_test/fake_pu_img1.jpg").unlink()
    (vlsp / "dataset/law_db/images.fld/image001.png").write_bytes(b"another figure")
    with pytest.raises(SystemExit, match="lacks 1 file.* 1 with different content") as e:
        nl.build(tmp / "layer", vlsp, tmp / "rebuilt")
    assert "fake_pu_img1" not in str(e.value) and not (tmp / "rebuilt").exists()


def test_a_changed_layer_is_refused(world):
    tmp, nat, vlsp = world
    nl.export(nat, tmp / "layer", repo=tmp / "repo")
    p = tmp / "layer" / "dataset" / nl.SPLITS["train"][0] / nl.SPLITS["train"][1]
    p.write_text("[]")
    with pytest.raises(SystemExit, match="missing or changed"):
        nl.build(tmp / "layer", vlsp, tmp / "rebuilt")


def test_the_layer_is_never_written_inside_the_repository(world):
    tmp, nat, _ = world
    with pytest.raises(SystemExit, match="outside the repository"):
        nl.export(nat, tmp / "repo" / "layer", repo=tmp / "repo")
    with pytest.raises(SystemExit, match="outside the repository"):
        nl.export(nat, nl.ROOT / "naturalized_layer_probe")
    assert not (nl.ROOT / "naturalized_layer_probe").exists()


def test_it_never_writes_into_a_folder_that_is_not_empty(world):
    tmp, nat, vlsp = world
    _write(tmp / "busy" / "x.txt", "x")
    with pytest.raises(SystemExit, match="not empty"):
        nl.export(nat, tmp / "busy", repo=tmp / "repo")
    nl.export(nat, tmp / "layer", repo=tmp / "repo")
    with pytest.raises(SystemExit, match="not empty"):
        nl.build(tmp / "layer", vlsp, tmp / "busy")


def test_an_unknown_split_is_refused(world):
    tmp, nat, _ = world
    with pytest.raises(SystemExit, match="unknown split"):
        nl.export(nat, tmp / "layer", repo=tmp / "repo", splits=("dev",))


def test_a_vlsp_json_with_the_same_content_but_other_formatting_is_accepted(world, capsys):
    tmp, nat, vlsp = world
    nl.export(nat, tmp / "layer", repo=tmp / "repo")
    (vlsp / "dataset/law_db/vlsp2025_law.json").write_text('{ "law" : 1 }\n')            # same content
    out = nl.build(tmp / "layer", vlsp, tmp / "rebuilt")
    assert out["same_content_other_formatting"] == 1
    (vlsp / "dataset/law_db/vlsp2025_law.json").write_text('{"law": 2}')                  # other content
    with pytest.raises(SystemExit, match="1 with different content"):
        nl.build(tmp / "layer", vlsp, tmp / "rebuilt2")
