# Where this code comes from

`services/rag/` is the RAG project, imported into `ns-vqa` on 2026-11-21 (plan: `docs/plans/rag-import.md`).

- **Source:** the private repository `trafficvqa-rag`, branch `exp/option-c`, commit `a081015` (local tag `archive-before-import`).
- **What was imported:** the code only (`src/`, `experiments/`, `pyproject.toml`, `README.md`, `.gitignore`, `VN_MTEB_vie_v1_summary.csv`), with its history, moved under `services/rag/` with `git filter-repo`.
- **What was left out of git:**
  - `artifacts/` (the index, captions, embeddings, saved runs) and `reports/` (spreadsheets);
  - every private-test file.

  The runtime files live in `services/rag/` but are gitignored.
- **Identity (owner's instruction, 2026-11-21):** author and committer of every imported commit, and of the merge commit, are `stfutien <nhuttien25.25@gmail.com>`. Commit messages are unchanged, including their `Co-Authored-By` lines.
- **Hashes changed** because the files and paths changed. Two commits that touched only `artifacts/` or `reports/` became empty and were dropped.

The code in `services/rag/` is byte-identical to `a081015` for every imported path.

## Old to new commits

Citations of `trafficvqa-rag@<hash>` (status.md, the thesis) map to `ns-vqa` like this:

| trafficvqa-rag | ns-vqa | date | subject |
|---|---|---|---|
| `d6b7a73` | `cd63b83` | 2026-11-14 | Initial commit: add RAG pipeline and experiment results |
| `7055d83` | `6d30022` | 2026-11-19 | Restore src/text_based_rag/inference.py from its compiled bytecode |
| `998dd85` | `c5bc9af` | 2026-11-19 | Merge pull request #1 from lephuocloc1729/restore-inference-module |
| `54ecf61` | dropped | 2026-11-19 | Replace private report spreadsheets with Natural_Private_Benchmark.xlsx |
| `fb5f34a` | `b5af125` | 2026-11-19 | Update README now that inference.py is restored |
| `0407209` | `e6d5ca7` | 2026-11-19 | Merge branch 'restore-inference-module' |
| `7fe53e8` | dropped | 2026-11-19 | Remove earlier private exploration runs; keep the final Qwen Q4 / BF16 private runs |
| `4364929` | `6347a6e` | 2026-11-19 | Option C experiment: --kb-articles appends knowledge-base articles after retrieval; offline retrieval check |
| `1b36e81` | `44e5356` | 2026-11-21 | Live private run on a subset of question ids |
| `db75c4b` | `f177426` | 2026-11-21 | Live private run: private questions live, offline index from cache |
| `a081015` | `4a5c81c` | 2026-11-21 | add new experiment |

## Behaviour checks done before the import (2026-11-21)

On the original folder, config C (the README's run command):

- **Retrieval, Mac, cached embeddings:** the same law, chunk and few-shot ids, ranks and gates as the saved runs, on all 100 public questions (against `public_fewshot_C_0/1/3`) and all 146 private questions (against `private_models_Qwen_Q4_run1`). Scores agree to 3e-7; query embeddings are bit-identical.
- **Answers, RTX 5090, cached captions and embeddings:** 10 private questions answered identically to the saved Q4 runs 1 and 2 (text, analysis, few-shots, tokens). Peak GPU memory was 9,288 MiB, and the mean was 4.08 s per answer.

The same checks are to be re-run from `services/rag/` (plan S6).
