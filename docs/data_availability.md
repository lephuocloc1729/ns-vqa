# Data availability statement

2026-11-25. Contact for the data: **lephuocloc1729@gmail.com**.

## The statement

The evaluation uses **VLSP2025-MLQA-Natural**, a free-text ("natural") question-answering version of the VLSP 2025
MLQA-TSR dataset [VLSP 2025 MLQA-TSR, https://aclanthology.org/2025.vlsp-1.48/], made for this project. It has 530
training, 100 public test and 146 private test questions.

- **What is VLSP's:** the road photos, the legal corpus (`law_db`, with its figures) and the questions, which come
  from the original release, with the author's edits to some questions. They are distributed by the VLSP 2025
  organisers under their data agreement, and they are **not redistributed** with this project.
- **What is the author's:** the natural answers, the edits to the questions, the question types of the test
  splits, and the review of the training split. Together with a list of sha256 hashes for every file of the
  finished dataset, they form an **annotation layer** (`tools/naturalized_layer.py`).
- **Availability of the layer:** on request, by email to lephuocloc1729@gmail.com, for researchers who hold the
  VLSP 2025 data agreement. It covers the training, public test and private test splits. Please don't redistribute
  it, and keep the private test answers out of any training or tuning, so that the private test stays a clean
  benchmark.
- **Rebuilding the dataset:** with the original VLSP release and the layer,
  `tools/naturalized_layer.py build --layer <layer> --vlsp <VLSP release> --out VLSP2025-MLQA-Natural` finds each
  VLSP file, checks it against the layer's hashes and rebuilds the dataset exactly as used here. Copies of the VLSP
  release that differ only in the formatting of a JSON file are accepted and reported.
- **The RAG's corpus and few-shot files** are built from the same data and are available under the same
  conditions. The RAG's model weights are public (sources and sha256 in `docs/release/v1.0-benchmark.md`).
- **What can be checked without any of these data:** the code, the frozen configuration and its freeze check
  (tag `v1.0-benchmark`), the test suite, the Docker stack, and the committed records of the three private
  benchmark runs (`eval/private_ran*.json`, `eval/private_rag_ran*.json`).

## A shorter version for the thesis

> The evaluation data are a free-text version of the VLSP 2025 MLQA-TSR dataset, made for this work. The photos,
> the legal corpus and the questions belong to the VLSP 2025 release and are not redistributed, under its data
> agreement. The author's annotations (the free-text answers, the question edits and a hash list of every file)
> are available by email (lephuocloc1729@gmail.com) to holders of the VLSP 2025 data agreement, with a script that
> rebuilds the dataset exactly from the original release (`tools/naturalized_layer.py`). The code, the frozen configuration
> and the records of every benchmark run are public at https://github.com/lephuocloc1729/ns-vqa.

## For the owner: making and sharing the layer

```bash
.venv/bin/python tools/naturalized_layer.py export --out ~/naturalized_layer --include-private   # all three splits
.venv/bin/python tools/naturalized_layer.py export --out ~/naturalized_layer_tp                    # train + public only
```

- The layer is written outside the repository only, and never committed: it holds the dataset's text.
- `provenance.json` is left out unless `--with-provenance` is given, since it quotes VLSP's original samples
  (choices and answers); no code reads it.
- Checked on 2026-11-25: the layer (5 text files, 752 KB, plus the hashes of 1,971 VLSP files) rebuilds the train
  and public test splits and `law_db` byte for byte, apart from `provenance.json`; with another copy of the VLSP
  `law_db` JSON (same content, different formatting) the rebuild is accepted and reported.
- The private test is exported only with `--include-private` (owner, 2026-11-25). Besides the scoring code, the
  export is the only code allowed to name its answer file, and it copies the file without reading it
  (`tests/test_leakage_guard.py`).
- Checked on 2026-11-25 with `--include-private`: 6 text files (820 KB) plus the hashes of 2,075 VLSP files rebuild
  all three splits and `law_db` byte for byte, apart from `provenance.json`.
- Before sending it: check that the requester holds the VLSP 2025 data agreement. Telling the VLSP 2025 organisers
  and the supervisor is still advisable, since the answers are built on VLSP's questions.
