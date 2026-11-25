# Data availability statement

**Draft (2026-11-25), for the owner's decision.** The parts in [brackets] depend on what the VLSP 2025 organisers
and the supervisor allow; choose one option in each and delete the rest.

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
- **Availability of the layer:** [option A: on request from the author, to researchers who hold the VLSP 2025
  data agreement.] [option B: on Hugging Face at <link>, with access granted to holders of the VLSP 2025 data
  agreement.] The layer covers the training and public test splits. **The private test split is not part of it:**
  only the project's scoring code reads its answers, so it is [available on request only, after the organisers
  agree] [not shared].
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
> for the training and public test splits are available [on request / at <link>] to holders of the VLSP 2025 data
> agreement, with a script that rebuilds those splits exactly from the original release (`tools/naturalized_layer.py`). The code, the frozen configuration
> and the records of every benchmark run are public at https://github.com/lephuocloc1729/ns-vqa.

## For the owner: making and sharing the layer

```bash
.venv/bin/python tools/naturalized_layer.py export --out ~/naturalized_layer                 # train + public test
.venv/bin/python tools/naturalized_layer.py export --out ~/naturalized_layer_train --splits train
```

- The layer is written outside the repository only, and never committed: it holds the dataset's text.
- `provenance.json` is left out unless `--with-provenance` is given, since it quotes VLSP's original samples
  (choices and answers); no code reads it.
- Checked on 2026-11-25: the layer (5 text files, 752 KB, plus the hashes of 1,971 VLSP files) rebuilds the train
  and public test splits and `law_db` byte for byte, apart from `provenance.json`; with another copy of the VLSP
  `law_db` JSON (same content, different formatting) the rebuild is accepted and reported.
- The private test can't be exported: only `eval/e2e_private.py` may name its answer file
  (`tests/test_leakage_guard.py`). Sharing it would need that rule changed first, which is the owner's decision.
- Ask the VLSP 2025 organisers, and the supervisor, before sharing it with anyone.
