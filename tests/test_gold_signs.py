"""Gold-sign tooling, offline: set-T selection, label validation, private routing,
the cost estimate. No API calls and no dataset files (inputs are hand-made)."""

import json
from types import SimpleNamespace

import pytest
import yaml

import eval.gold_signs as gs
from vqa.llm.spend import SpendLimitExceeded

# ---------------------------------------------------------------- select

TRAIN = [f"train_1_{k}" for k in range(1, 21)]
QUESTIONS = [{"id": f"train_{k}", "image_id": f"train_1_{k}",
              "question": ["Tốc độ tối đa là bao nhiêu km/h?", "Xe tải có được rẽ trái không?",
                           "Đây là biển báo gì?", "Làn nào dành cho ô tô?"][k % 4]}
             for k in range(1, 21)]
DEV = {"public_test_1_1", "public_test_1_2", "public_test_9_9"}   # stands for all public images
GROUPS = [
    {"images": [{"split": "public", "image_id": "public_test_1_1"},
                {"split": "train", "image_id": "train_1_3"}, {"split": "train", "image_id": "train_1_4"}]},
    {"images": [{"split": "private", "image_id": "q_1"}, {"split": "train", "image_id": "train_1_5"}]},
    {"images": [{"split": "public", "image_id": "public_test_8_8"},   # not in the given set
                {"split": "train", "image_id": "train_1_6"}]},
    {"images": [{"split": "train", "image_id": "train_1_7"},
                {"split": "public", "image_id": "public_test_1_2"}]},
]


def test_select_excludes_train_images_duplicated_with_public_images():
    picked = gs.pick_set_t(TRAIN, QUESTIONS, DEV, GROUPS, n=20)
    assert {"train_1_3", "train_1_4", "train_1_7"}.isdisjoint(picked)
    # duplicates of private images (or of images outside the given set) are not excluded
    assert {"train_1_5", "train_1_6"} <= set(picked)
    assert len(picked) == 17 and len(set(picked)) == 17


def test_select_is_deterministic():
    a = gs.pick_set_t(TRAIN, QUESTIONS, DEV, GROUPS, n=8)
    b = gs.pick_set_t(list(reversed(TRAIN)), list(reversed(QUESTIONS)), set(DEV), GROUPS, n=8)
    assert a == b and len(a) == 8
    assert gs.pick_set_t(TRAIN, QUESTIONS, DEV, GROUPS, n=8, seed=1) != a or len(TRAIN) < 9


def test_select_spreads_over_categories():
    picked = gs.pick_set_t(TRAIN, QUESTIONS, DEV, GROUPS, n=4)
    cats = {gs.category(q["question"]) for q in QUESTIONS if q["image_id"] in picked}
    assert len(cats) == 4


def test_committed_set_t_has_no_public_dev_duplicate():
    data = json.loads(gs.SET_T.read_text())
    dups = json.loads(gs.DUPLICATES.read_text())
    banned = gs.excluded_train_images(gs.dev_images(), dups["groups"])
    assert 30 <= data["n"] == len(data["images"]) <= 40
    assert not banned & set(data["images"])
    assert all(i.startswith("train_") for i in data["images"])
    assert set(data) == {"seed", "n", "method", "excluded_train_images", "pool", "images"}


def test_committed_set_t_shares_no_group_with_any_public_image():
    """Neither half of the public test: read straight from the duplicate groups."""
    t = set(json.loads(gs.SET_T.read_text())["images"])
    for g in json.loads(gs.DUPLICATES.read_text())["groups"]:
        ids = {i["image_id"] for i in g["images"]}
        if any(i["split"] == "public" for i in g["images"]):
            assert not t & ids, f"set T shares a duplicate group with a public image: {t & ids}"


def test_public_images_cover_both_halves():
    split = json.loads(gs.SPLIT_FILE.read_text())
    halves = [set(v["images"]) for v in split.values() if isinstance(v, dict)]
    assert len(halves) == 2 and gs.public_images() == halves[0] | halves[1]
    assert len(gs.public_images()) == 90


# ---------------------------------------------------------------- label validation

def label(**over):
    doc = {"image_id": "train_1_3", "split": "train", "status": "done", "violation_question": False,
           "signs": [{"code": "P.127", "value": 50, "unit": "km/h", "shape": "circle", "border": "red",
                      "background": "white", "position": {"rank_top_down": 1, "side": "right"},
                      "plates": [{"kind": "time", "text": "6h-22h",
                                  "time_windows": [{"start": "06:00", "end": "22:00"}]}]}],
           "vehicles": [], "notes": ""}
    doc.update(over)
    return doc


def sign(**over):
    s = {"code": "P.123a", "shape": "circle", "border": "red", "background": "white"}
    s.update(over)
    return s


def test_a_good_label_passes():
    rec, errs = gs.check_label(label())
    assert errs == []
    assert rec["signs"][0]["code"] == "P.127" and rec["signs"][0]["readable"] is True
    assert rec["signs"][0]["plates"][0]["time_windows"] == [{"start": "06:00", "end": "22:00"}]


@pytest.mark.parametrize("code, ok", [
    ("P.999", False),          # not in the catalog
    ("X.123", False),
    ("", False),
    ("W.207c", True),          # a variant of a family row
    ("W.207(a,b,c,d,e,f,g,h,i,k,l)", True),  # the family row itself
    ("W.207", True),           # the stem of a family row
    ("W.221", False),          # a stem of separate rows: give the variant
])
def test_codes_are_checked_against_the_catalog(code, ok):
    _, errs = gs.check_label(label(signs=[sign(code=code)]))
    assert (errs == []) is ok, errs


def test_unknown_only_when_unreadable():
    assert gs.check_label(label(signs=[sign(code="UNKNOWN")]))[1]
    rec, errs = gs.check_label(label(signs=[sign(code="UNKNOWN", readable=False)]))
    assert errs == [] and rec["signs"][0]["readable"] is False


@pytest.mark.parametrize("plate", [
    {"kind": "sticker", "text": "x"},                                      # unknown kind
    {"kind": "time", "time_windows": [{"start": "6h", "end": "22:00"}]},  # bad HH:MM
    {"kind": "local"},                                                     # local plate without text
    {"kind": "time", "actions": ["park"]},                                 # actions on a standard plate
    {"kind": "vehicle", "vehicles": [{"class": "spaceship"}]},             # unknown vehicle class
    {"kind": "time", "colour": "red"},                                     # unknown field
])
def test_bad_plates_are_rejected(plate):
    _, errs = gs.check_label(label(signs=[sign(plates=[plate])]))
    assert errs


def test_other_bad_labels():
    assert gs.check_label(label(signs=[sign(position={"box": [1, 2, 3, 4]})]))[1]  # no boxes
    assert gs.check_label(label(signs=[sign(readable="yes")]))[1]
    assert gs.check_label(label(split="public_holdout_x"))[1]
    assert gs.check_label(label(extra=1))[1]
    car = [{"class": "car", "lane": 1, "action": "park"}]
    assert gs.check_label(label(vehicles=car))[1]                       # no violation question
    assert gs.check_label(label(vehicles=car, violation_question=True))[1] == []
    assert gs.check_label(label(split="private", vehicles=car, violation_question=True))[1]


# ---------------------------------------------------------------- import and private routing

@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "WORK", tmp_path / "work")
    monkeypatch.setattr(gs, "dev_images", lambda: {"public_test_1_1"})
    monkeypatch.setattr(gs, "set_t_images", lambda: ["train_1_3"])
    monkeypatch.setattr(gs, "TRAIN_QA", tmp_path / "missing.json")
    return tmp_path


def write_yaml(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True))


def test_import_writes_done_labels_and_skips_todo(work):
    write_yaml(work / "work/labels/train/train_1_3.yaml", label())
    write_yaml(work / "work/labels/public_dev/public_test_1_1.yaml",
               label(image_id="public_test_1_1", split="public_dev", status="todo"))
    out = work / "gold.jsonl"
    gold = gs.import_labels(out=out)
    assert [g["image_id"] for g in gold] == ["train_1_3"]
    assert json.loads(out.read_text().splitlines()[0])["signs"][0]["code"] == "P.127"


def test_import_refuses_unknown_codes_and_images_outside_the_gold_sets(work):
    write_yaml(work / "work/labels/train/train_1_3.yaml", label(signs=[sign(code="P.999")]))
    with pytest.raises(SystemExit, match="P.999"):
        gs.import_labels(out=work / "gold.jsonl")
    write_yaml(work / "work/labels/train/train_1_3.yaml", label(image_id="train_9_9"))
    with pytest.raises(SystemExit, match="not a train image"):
        gs.import_labels(out=work / "gold.jsonl")


def test_import_refuses_private_labels_in_the_public_folder(work):
    write_yaml(work / "work/labels/train/train_1_3.yaml", label(split="private"))
    with pytest.raises(SystemExit, match="--private"):
        gs.import_labels(out=work / "gold.jsonl")


def test_anchoring_counts_signs_kept_from_the_draft(work):
    rec, _ = gs.check_label(label())
    draft = {"signs": [label()["signs"][0], sign()]}
    assert gs.anchoring(rec["signs"], draft) == {"draft_signs": 2, "kept_unchanged": 1, "draft_valid": True}
    assert gs.anchoring(rec["signs"], None) is None


def test_private_labels_go_only_to_the_ignored_private_path(tmp_path):
    rows = [{"image_id": "q_1", "split": "private", "signs": [], "vehicles": []}]
    for elsewhere in (tmp_path / "gold.jsonl", gs.GOLD, gs.PRIVATE_OUT / "other.jsonl"):
        with pytest.raises(SystemExit, match="refusing"):
            gs.write_gold(rows, elsewhere)
    with pytest.raises(SystemExit, match="mix"):
        gs.write_gold(rows + [{"image_id": "train_1_3", "split": "train"}], gs.PRIVATE_GOLD)
    with pytest.raises(SystemExit, match="private folder"):
        gs.write_gold([{"image_id": "train_1_3", "split": "train"}], gs.PRIVATE_OUT / "x.jsonl")


def test_private_write_refused_if_git_does_not_ignore_it(monkeypatch):
    monkeypatch.setattr(gs, "is_gitignored", lambda p: False)
    with pytest.raises(SystemExit, match="does not ignore"):
        gs.write_gold([{"image_id": "q_1", "split": "private"}], gs.PRIVATE_GOLD)


def test_private_path_and_working_files_are_gitignored():
    assert gs.is_gitignored(gs.PRIVATE_GOLD)
    assert gs.is_gitignored(gs.PRIVATE_OUT / "labels" / "q_1.yaml")
    assert gs.is_gitignored(gs.WORK / "drafts.jsonl")
    assert gs.is_gitignored(gs.WORK / "labels" / "train" / "train_1_3.yaml")
    assert not gs.is_gitignored(gs.GOLD)
    assert not gs.is_gitignored(gs.SET_T)


# ---------------------------------------------------------------- estimate and prefill

def test_native_size_and_image_tokens():
    assert gs.native_size(700, 476) == (700, 476)          # never upscaled
    w, h = gs.native_size(2496, 1402)
    assert max(w, h) <= 1568 and w * h <= 1_150_000 * 1.01
    assert gs.image_tokens(750, 100) == 101


def test_prefill_prompt_holds_the_guide_and_the_catalog():
    s = gs.prefill_system()
    assert "What counts as a sign" in s and "P.127" in s and "readable: false" in s


def test_prefill_stops_at_the_spend_guard(work, monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "targets", lambda: [("train_1_3", "train")])
    monkeypatch.setattr(gs, "violation_images", lambda: set())
    monkeypatch.setattr(gs, "image_block", lambda p: {"type": "text", "text": "img"})
    monkeypatch.setattr(gs, "image_path", lambda i, s: tmp_path / "x.jpg")

    class SDK:
        def __init__(self):
            self.messages = self
            self.created = 0

        def count_tokens(self, **kw):
            assert kw["model"] == gs.MODEL and kw["output_config"]["effort"] == gs.EFFORT
            return SimpleNamespace(input_tokens=13_000)

        def create(self, **kw):
            self.created += 1
            raise AssertionError("must not be sent")

    sdk = SDK()
    with pytest.raises(SpendLimitExceeded):
        gs.prefill(0.01, sdk=sdk)
    assert sdk.created == 0


class HTTPError(Exception):
    def __init__(self, msg, status_code, request_id):
        super().__init__(msg)
        self.status_code, self.request_id = status_code, request_id


@pytest.mark.parametrize("fail_on", ["count_tokens", "create"])
def test_prefill_logs_http_errors_and_reraises(work, monkeypatch, tmp_path, fail_on):
    monkeypatch.setattr(gs, "targets", lambda: [("train_1_3", "train")])
    monkeypatch.setattr(gs, "violation_images", lambda: set())
    monkeypatch.setattr(gs, "image_block", lambda p: {"type": "text", "text": "img"})
    monkeypatch.setattr(gs, "image_path", lambda i, s: tmp_path / "x.jpg")
    logged = []
    monkeypatch.setattr(gs, "log_call", logged.append)

    class SDK:
        def __init__(self):
            self.messages = self

        def count_tokens(self, **kw):
            if fail_on == "count_tokens":
                raise HTTPError("overloaded", 529, "req_count")
            return SimpleNamespace(input_tokens=100)

        def create(self, **kw):
            raise HTTPError("bad request", 400, "req_create")

    with pytest.raises(HTTPError):
        gs.prefill(1.0, sdk=SDK())
    assert len(logged) == 1
    rec = logged[0]
    assert rec["status"] == "http_error" and rec["call"] == fail_on and rec["cost_usd"] == 0.0
    assert rec["http_status"] == (529 if fail_on == "count_tokens" else 400)
    assert rec["request_id"] == ("req_count" if fail_on == "count_tokens" else "req_create")
    assert rec["error"] in ("overloaded", "bad request") and rec["image_id"] == "train_1_3"
    assert not gs.drafts_path().exists()   # nothing recorded as a draft
