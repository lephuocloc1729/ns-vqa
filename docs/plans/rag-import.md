# Plan: import the RAG into ns-vqa (`services/rag/`)

**Status: proposed (2026-11-21, revision 2), not approved.** Nothing has been run.

**Revision 2:** the asset sources are the Mac's RAG folder plus public downloads. No GPU machine's files are needed (S0); the `query/` caches are provenance only; weights are never downloaded to the Mac.

**Revision 3:**
- S6-D compares the original checkout and the import on the same GPU, back to back, not the import against the saved public run. Live runs repeat each other exactly but do not reproduce the saved batch runs: 33 of 50 and 34 of 48 identical on private, status.md.
- S1 and S6-C use config C's flags.
- The Mac venv is the light one.

## Goal

The RAG (`trafficvqa-rag`, local folder `~/UNIVERSITY/Capstone/RAG`, branch `exp/option-c` at `a081015`) becomes part of `ns-vqa` under `services/rag/`:

- **Same behaviour:** the same retrievals and the same answers as the original, checked by the acceptance tests below.
- **Self-contained:** every file it needs (code, index, captions, dataset, model weights, llama.cpp binary) is inside `ns-vqa/services/rag/`. Once the checks pass, the original folder and repo are no longer needed.
- **Authorship (owner, 2026-11-21):** every imported commit has author and committer `stfutien <nhuttien25.25@gmail.com>`.

## What goes in git, and what doesn't

| Kind | Where in `services/rag/` | In git? |
|---|---|---|
| Code: `src/`, `experiments/`, `pyproject.toml`, `README.md`, `.gitignore` | as in the original | **yes**, with history |
| Asset manifest: every runtime file's path, size, sha256 and source | `assets_manifest.yaml` | **yes** |
| Fetch and verify scripts | `scripts/fetch_assets.sh`, `scripts/verify_assets.py` | **yes** |
| Origin record: source repo, branch, old → new hashes | `ORIGIN.md` | **yes** |
| The index: law-corpus chunks and vectors, train-bank captions and embeddings, as config C reads them | `artifacts/` | no, gitignored |
| The dataset: VLSP2025-MLQA-Natural, the TSR `law_db` and law images | `data/raw/`, `data/processed/` | no, gitignored |
| Model weights: Qwen3.5-9B Q4_K_M + `mmproj-F16`, `f2llm-v2-0.6b` (BF16 GGUF only for the optimisation table) | `models/huggingface/`, **on CUDA machines only** | no, gitignored; listed in the manifest with URL, revision and sha256 |
| llama.cpp b11624 (Linux CUDA 12.8 build), the PyTorch cu130 wheels | `.venv/tools/llama.cpp-b11624/`, the RAG's venv, **CUDA machines only** | no; URL and sha256 in the manifest |
| Evidence behind reported numbers: saved predictions (public; private Q4 run1 and run2, BF16), `outputs/latency/`, the live-run outputs, the tuning reports | `evidence/` | no, gitignored |

"All in this project" therefore means **all in the `ns-vqa` folder,** with git holding the code, the manifest and the scripts. Git never holds the data, for three reasons:

- CLAUDE.md: "never copy dataset files into the repo";
- the index is built from the course dataset;
- size: about 1 GB of data plus about 7 GB of weights.

A clean machine gets the data from a private bundle (the index, dataset-derived files and evidence) plus public downloads (the weights and llama.cpp from Hugging Face and the ggml-org releases), all checked against the manifest.

Private-test files (the saved private predictions, the live private outputs, `Natural_Private_Benchmark.xlsx`) are copied **unopened** into `evidence/private/`, because `eval/e2e_private_rag.py` needs the saved predictions to reproduce B2 and V2. No code or person reads them except the scoring code, as now.

## Steps

### S0. Before starting

- **The asset sources are known; nothing has to be recovered from the GPU machine.**
  - The GPU machine of 21/11 got the code and `artifacts/` (808 files, 27 MB) from this Mac by rsync.
  - It downloaded the rest from public sources:
    - `huggingface.co/unsloth/Qwen3.5-9B-GGUF`;
    - `github.com/ggml-org/llama.cpp/releases/download/b11624`;
    - the PyTorch cu130 wheel index.
  - So the sources are the Mac's RAG folder plus those URLs, at pinned revisions and sha256s.
- **The `query/` folder is provenance only.**
  - Some `run_config.json` files (e.g. `natural_qa/t768_o64/f2llm-v2-0.6b/train/run_config.json`) pin hashes of `artifacts/experiments/text_based_rag/query/...`. These record how the train bank was first built.
  - Config C runs with `--fresh-captions`, which reads train captions through `load_fresh_caption_artifacts` (`natural_qa_runner.py:1618`) from `natural_qa/image_captioning/train`, which is on the Mac. Only `load_existing_captions` (line 827) and the older `query_embedding.py` / `query_retrieval.py` read `query/`.
  - The manifest lists those entries as "provenance only, not a runtime input". The old non-fresh pipelines cannot be re-run, and the README says so; config C is not affected.
- **Disk space:** the Mac has 2.9 GB free.
  - Weights (~7 GB) are never downloaded here; they run on CUDA only.
  - Only the manifest's runtime and evidence files are copied, not the whole 1.4 GB folder: other encoders, chunk sizes and tuning runs stay in the archive.
  - The dataset is a symlink if identical (D3).
- **Back up the original:** push `a081015` to `trafficvqa-rag` (private) and tag it `archive-before-import`.
- **Tools:** install `git-filter-repo`:
  ```bash
  brew install git-filter-repo
  ```

### S1. Inventory: what the RAG really reads

The README admits that its list of required assets is partial, so the inventory comes from tracing file opens, not from reading code. A small wrapper installs a Python audit hook (`sys.addaudithook`, event `open`) and records every path opened under the RAG root. It runs:

1. **On the Mac, first:** `--retrieval-only` on public_test with **config C's flags**:
   - `--fresh-captions --allow-incomplete-captions`;
   - `--corpus-chunks artifacts/experiments/text_based_rag/natural_qa/t768_o64/f2llm-v2-0.6b/train`;
   - `--embedding-model f2llm-v2-0.6b --reuse-precomputed-embeddings`;
   - `--corpus-k 5 --examples-k 4 --high-examples-k 3`, and the gates and weights of the README command.

   Only `--fresh-captions` takes the `load_fresh_caption_artifacts` path. Without it the runner falls into `load_existing_captions`, fails on the missing `query/` folder, and the trace proves nothing. If no traced open touches `query/`, that confirms S0.
2. **On a CUDA machine (any freshly rented GPU):** config C (the README's run command and `run_private_live.sh` flags) on 3 public_test questions: live captions, live embeddings, answer. This adds the model, llama.cpp and caption files to the list.

The union, plus every path pinned by a `run_config.json` / manifest hash check, becomes `assets_manifest.yaml`. Each entry gets a category (index, dataset, model, binary, evidence) and a source (bundle, or a download URL with its pinned revision).

Absolute paths stored in caches (the train captions hold `/Users/...` image paths) are checked in the trace. If the runner only stores them, nothing changes. If it opens them, the plan stops for a decision, because rewriting them changes hashed files.

### S2. Import the code, with history, under the new author

On a fresh clone in the scratchpad, never on the original folder:

```bash
git clone --no-local --branch exp/option-c ~/UNIVERSITY/Capstone/RAG rag-import
```
```bash
cd rag-import && git filter-repo \
  --path src/ --path experiments/ --path pyproject.toml --path README.md \
  --path .gitignore --path VN_MTEB_vie_v1_summary.csv \
  --mailmap ../rag-mailmap.txt --to-subdirectory-filter services/rag
```

`rag-mailmap.txt` maps both old identities to the new one. filter-repo applies a mailmap to authors and committers alike.

```text
stfutien <nhuttien25.25@gmail.com> PhuocLoc <lephuocloc1729@gmail.com>
stfutien <nhuttien25.25@gmail.com> Le Phuoc Loc <133197606+lephuocloc1729@users.noreply.github.com>
stfutien <nhuttien25.25@gmail.com> GitHub <noreply@github.com>
```

- Commit messages are unchanged, including the `Co-Authored-By` lines on 6 commits.
- Commits that only touched `artifacts/` or `reports/` become empty and are dropped: about 8 of 11 remain.
- **Check before merging:**
  - `git log --format='%an <%ae> | %cn <%ce>'` shows only stfutien;
  - `git ls-files` shows only `services/rag/...` (about 25 files);
  - no path in any commit contains `private`, `predictions`, `retrievals` or `.xlsx`;
  - no file is over 1 MB.

Then, in `ns-vqa`, on a new branch `task3/rag-import` from `main`, with the merge commit also as stfutien (D2):

```bash
git remote add rag-import ../rag-import && git fetch rag-import
```
```bash
GIT_AUTHOR_NAME=stfutien GIT_AUTHOR_EMAIL=nhuttien25.25@gmail.com \
GIT_COMMITTER_NAME=stfutien GIT_COMMITTER_EMAIL=nhuttien25.25@gmail.com \
git merge --allow-unrelated-histories rag-import/exp/option-c \
  -m "Import the RAG (trafficvqa-rag exp/option-c a081015, code only) under services/rag"
```
```bash
git remote remove rag-import
```

`ORIGIN.md` gets filter-repo's commit map (old → new). It records that `trafficvqa-rag@db75c4b`, the commit cited for the live run, is `ns-vqa@<new hash>`.

### S3. Bring the assets into the project

- Copy every manifest entry whose source is the Mac folder into `services/rag/`, keeping the original relative paths. The code resolves paths from its own root, so it runs unchanged from `services/rag/`.
- **Dataset (D3):** `ns-vqa` already has `VLSP2025-MLQA-Natural/`. If it is byte-identical to the RAG's copy (compared by the manifest), `services/rag/data/raw/VLSP2025-MLQA-Natural` is a relative symlink to it, so one copy serves both. Otherwise it is a copy. The TSR dataset (`law_db/vlsp2025_law.json`, the law images) is copied: only the RAG uses it.
- **Weights and llama.cpp (on CUDA machines only; on the Mac the manifest and the script are enough):** `scripts/fetch_assets.sh` downloads from `unsloth/Qwen3.5-9B-GGUF` and the `f2llm-v2-0.6b` repo at pinned revisions, and the ggml-org b11624 release assets named in the README. It refuses any file whose sha256 is not the manifest's (Q4_K_M `03b74727…`, mmproj `f70dc350…`).
- `scripts/verify_assets.py` checks every manifest entry (present, size, sha256) and prints what is missing. Docker and the service run it at start.
- **The private bundle:** everything in the manifest that is not a public download, as one archive, shared privately (Drive or a private release). `fetch_assets.sh --bundle <file>` unpacks it and verifies it.

### S4. Environment

- `services/rag/` keeps its own `pyproject.toml` and its own virtual environment. It is never installed into the rules' `.venv`, because its CUDA stack would break the Mac setup.
- **On the Mac, the light environment only:** numpy, requests and pillow, as in the original folder's `.venv` today (78 MB). That is enough for `--retrieval-only` from reused embeddings, `--help` and the asset checks. No PyTorch on the Mac; the full CUDA environment exists only on GPU machines.
- A version lock, `services/rag/requirements-gpu.txt`: `pip freeze` from the GPU machine's environment that made the saved runs. If that environment is gone, a lock from the S6-D run, which is then the reference.
- The Docker image (day 4) builds from this lock and the manifest.

### S5. Wire it into ns-vqa

- `eval/e2e_private_rag.py`, its docstring and status.md: `<RAG repo>` → `services/rag`. Default paths point to `services/rag/evidence/...`.
- **CLAUDE.md:** add the `services/rag/` layout line; the leakage guard still covers `vqa/` and `app/` only (owner decision of 2026-11-20); the asset and evidence rules above.
- **CI:** a second job installs the RAG's CPU-only dependencies, byte-compiles `services/rag/src`, runs `natural_qa_runner --help`, and checks that `assets_manifest.yaml` is well-formed. No assets in CI.
- Root `.gitignore`: `services/rag/{data,artifacts,models,evidence,outputs,.venv}`.

### S6. Acceptance: proof that it behaves the same

| Check | Where | Pass when |
|---|---|---|
| A. Code | Mac | every imported file in `services/rag/` is byte-identical to `a081015` (`git diff` of the trees is empty) |
| B. Assets | Mac + GPU | `verify_assets.py`: all manifest entries present, sha256 equal to the originals |
| C. Retrieval | Mac, no GPU | `--retrieval-only` with config C's flags (S1 step 1), run from the original folder and from `services/rag/`: the same chunk and example ids, order and scores (to 1e-6) on all 100 public questions |
| D. Answers | one rented GPU | config C, live captions and embeddings, on the same 100 public questions, **back to back:** once from the original checkout (`a081015`, its own folder) and once from `ns-vqa/services/rag/`, same machine and environment. Pass: answers and retrievals identical on **100 of 100** between the two runs |
| E. ns-vqa | Mac + CI | full suite green, leakage guard green, CI green on the branch |

- **Why D compares two live runs:** live runs repeat each other exactly (50 of 50 on a second pass, 21/11), but they do not reproduce the saved batch runs (33 of 50 and 34 of 48 identical on private). So matching the saved public answers would fail even for a perfect import. The match with the saved public run is reported as an extra figure; it does not decide pass or fail.
- The private test is not re-run: it is the benchmark, and C and D on public test the same code and assets.
- A failure on C or D stops the cut-over. The thesis numbers stay with the original repo until the cause is found.

### S7. Cut-over

- Open a PR `task3/rag-import` → `main`.
- After it is merged, the original `trafficvqa-rag` README gets one line ("moved to ns-vqa/services/rag"), and the GitHub repo is archived (owner, read-only, nothing deleted).
- The local `~/UNIVERSITY/Capstone/RAG` folder can be deleted by the owner, **only** after B, C and D pass and the bundle has been checked on a second machine.

## Decisions (owner)

| # | Question | Recommendation |
|---|---|---|
| D1 | A rented CUDA machine for S1 step 2 and S6-D (any fresh one; the files come from the Mac and public URLs) | One session of about 30 minutes |
| D2 | Is the merge commit itself also by stfutien? | Yes, so the whole import is one identity |
| D3 | Dataset: symlink to ns-vqa's copy if identical, or a separate copy? | Symlink if identical |
| D4 | Download the BF16 GGUF (~18 GB) now, or only when the Q4 vs BF16 table is measured? | Only for the table |
| D5 | Private evidence (saved private predictions, live outputs, `Natural_Private_Benchmark.xlsx`) copied unopened into `evidence/private/`? | Yes, so B2 and V2 stay reproducible without the original |

## Authorship note

The imported commits were written under PhuocLoc and will show stfutien (owner's instruction, 2026-11-21). The commit messages and the `Co-Authored-By` lines are kept as they are. **Owner to check:** the thesis's credit for who built the RAG (acknowledgements, team roles) should match what the history shows.

## Cost and time

- No Claude API calls.
- About half a day of work on the Mac.
- On a rented GPU: the trace (S1 step 2) and check D, about 30 minutes in all including model loading.
- On the Mac: only the runtime and evidence files from the folder, well under 1 GB, plus the light venv (~80 MB); no weights, no PyTorch. That fits in the 2.9 GB free.
- On the GPU: about 7 GB of downloads.
