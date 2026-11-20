# Plan: the owner's RAG system as the answer fallback

**Status: approved (owner, 2026-11-20)**, with decisions G1–G8 at the end. **Revised the same day (owner):** the RAG is the only fallback (no Sonnet fallback); the private benchmark runs once on `phase52` with the answer fallback off, and the RAG's saved, deterministic private answers are merged in afterwards (F4). No phase53 freeze is needed for the benchmark.

## Why

- The rules decide only part of the questions. Every other question (unknown, uncertain, out of scope, a failed parse, no scene) goes to the answer fallback, today one Sonnet 5.5 vision call (`vqa/answer/fallback.py`, prompt `answer_fallback/v2`).
- The owner's RAG project (`~/UNIVERSITY/Capstone/RAG`, "Vietnamese Legal RAG") answers the same dataset with law retrieval from `law_db` and a local Qwen3.5-9B through llama.cpp. As the fallback it would:
  - give fallback answers **cited law passages** (file, article, chunk), which the Sonnet fallback lacks (checklist 1.3 and 1.6);
  - run **locally**, with no per-question API cost for the fallback;
  - bring its **Q4 vs BF16** comparison for checklist items 1.4 and 1.5 (quantization, latency, VRAM, accuracy).
- RAG alone is also an ablation row in Chapter 4 (F5).

## The RAG is used as it is (owner, 2026-11-20)

**Owner decision:** the RAG keeps its train few-shots and example-guided law retrieval, chosen by similarity; the dataset is the course's, and its train split may be used freely. CLAUDE.md's leakage guard keeps applying to the rules side (`vqa/`) only; a line saying so is added to CLAUDE.md when the plan is approved.

## F1. Pin the RAG's existing configuration (RAG repo, no code change)

- **The configuration of the saved runs, unchanged:** Qwen3.5-9B Q4_K_M through llama.cpp b11624, `f2llm-v2-0.6b` embeddings, `--fewshot-k 5 --answer-with-images`, `--corpus-k 5 --examples-k 4 --high-examples-k 3`, `--gate-low 0.70 --gate-high 0.7835`, `--weight-high 0.87 --weight-middle 0.05 --weight-low 0.40`, `--context-size 65536 --current-context-budget 20000 --answer-max-tokens 2048` (the README's run command). The owner confirms these are the flags of the runs to keep (G2).
- Record the configuration (model file SHA-256s, llama.cpp build, flags, corpus and train-bank fingerprints) in one version string, like the prompt versions here.

## F2. A single-question RAG service (RAG repo)

Today `natural_qa_runner` runs over a whole split with precomputed captions and embeddings. The fallback needs one question at a time:

- **`POST /answer`**, with an image (bytes or path) and the question. Steps: caption, embed, corpus retrieval, answer. It returns JSON:
  - `answer` (text);
  - `verdict` (`yes` / `no` / `value` / `unknown`, using the same Đúng/Sai mapping as `vqa/answer/faithfulness.py`);
  - `citations` (`law_id`, `article_id`, chunk text and score);
  - `config_version`, timings per stage and token counts.
- **`GET /health`** and **`GET /version`.**
- Streaming (`text/event-stream`) for the demo UI (checklist 1.2). The evaluation runs use the non-streaming call.
- It runs on the NVIDIA GPU machine (CUDA, BF16; the README says the Mac cannot run it). The measured mean is about 12 s per question on public_test (caption 3.2 s, answer 8.1 s; `outputs/latency/latency_summary.json`).
- **Tests** in the RAG repo: the request and response schema, a fake model backend, and refusal of an unknown config version.

## F3. The fallback client in this repo (`vqa/answer/rag_fallback.py`)

- **`RagFallback.answer(image_path, question, scene) -> FallbackAnswer`**, the same interface as `AnswerFallback`, calling the service over HTTP with a timeout.
  - The URL comes from an environment variable (`VQA_RAG_URL`), never from a file in the repo.
  - The scene graph is not sent (G4).
- **`PipelineConfig.answer_fallback_kind: "claude" | "rag"`** (G1: `rag`; `claude` stays for the old records). It is a new switch, so it goes in `LATER_SWITCHES` for every existing profile, as `scene_rerun` did.
- **Answers are marked as fallback answers:**
  - `answered_by="fallback"` and `basis: ["fallback", "rag"]`;
  - the retrieved passages go in a separate `retrieved` field, **never** in `citations`, which stay the rule engine's. A RAG answer is never shown as a rule conclusion.
- **Failure handling:** if the service is down, times out or returns bad JSON:
  - the engine's own answer is used through the writer (as P3 does after a failed fallback today).
- **Leakage guard:** `vqa/` sends only the image and the question. The leakage tests still pass, since the client mentions no split, fixture or QA file.
- **Tests:** a fake HTTP server checks the trigger path, the timeout, that `citations` stay empty, and the trace fields (`config_version`, timings).

## F4. Evaluation (revised, owner 2026-11-20)

All figures are reported on all images only (owner, 2026-11-20: no non-duplicate figures; CLAUDE.md's "two scores" rule is relaxed), and judged with this project's judge (`eval/judge.py`), not the RAG project's own grader.

**The RAG is deterministic** (fixed seeds and temperature). Checked: its two saved Q4 private runs (`answer_comparison/private_models_Qwen_Q4_run1` and `_run2`) give identical answers on all 146 questions, and the latency re-run matched the cached public_test answers on 100 of 100. Those runs used exactly the F1 flags (`run_config.json`: 5 few-shots, `examples_k` 4, gates 0.70 / 0.7835, weights 0.87 / 0.05 / 0.40, `f2llm-v2-0.6b`, `qwen3.5-9b-gguf`). So the saved `predictions.jsonl` is the RAG's answer for every private question, and no GPU run is needed for the benchmark.

1. **(Recommended first) the v18 dev guardrail:** a re-parse of dev and dev2 with v18 on stored scenes, so the phase52 rules are checked before the one private run.
2. **The private run, once, on `phase52`, answer fallback off** (`eval/e2e_private.py`, changed to build its pipeline with `answer_fallback=False`). It gives **V1** (rules only: decided coverage, accuracy on decided, overall with non-decided counted wrong) and writes the replay records, which hold each question's trigger.
3. **The RAG merge, once** (`eval/e2e_private_rag.py`, new, scoring code like `e2e_private.py`). Inputs: the private run's `records.jsonl` and the RAG's `predictions.jsonl` (its path and sha256 go in the report). It refuses unless the private run has finished, the two files cover the same 146 questions, and its own sentinel `eval/private_rag_ran.json` does not exist. In memory it grades:
   - **V2:** the rules' answer where no trigger fired, the RAG's answer where one did;
   - **B2:** the RAG's answer for every question.
   It writes one aggregate file (no ids): overall, Yes/No and Natural QA scores for V2 and B2, the RAG's score on the triggered questions, by trigger, and the judge cost.
4. **public_dev (may be read question by question):** the same merge from stored pipeline records and the RAG's saved public_test answers, for the error analysis in Chapter 4.

The demo and the final repository use the RAG service (F2) and client (F3); a freeze record for that configuration is written when it is built.

## F5. Reporting (Chapter 4)

| Row | System |
|---|---|
| Baseline 1 | LowCost (VLSP 2025, Anh et al., paper 1.53), adapted to free-response Natural QA with Gemma 3 12B |
| Baseline 2 | LexiSignVQA (VLSP 2025, paper 1.52), adapted to free-response Natural QA with Gemma 3 12B |
| Proposed V1 | neuro-symbolic, rules only (the headline, as in the phase-5 plan) |
| Proposed V2 | neuro-symbolic + RAG fallback |
| Ablation | RAG alone, its existing configuration (F1; "B2" in F4.3) |

- **Baselines (owner, 2026-11-20):** the two published VLSP 2025 systems, cited, described as adapted re-implementations (the papers solved the multiple-choice TSR task; their reported numbers are not comparable). Claude alone (B1 Sonnet, 85.3% on private) is not reported at this time.
- **Same judge for every row:** the baselines' saved private answers are graded by this project's judge, through the same merge-style scoring as B2 (a predictions file in, aggregate out), not by their own graders. It is to be checked first that each baseline has saved free-response answers for all 146 private questions; a missing one needs a GPU run.

- Decided coverage and accuracy on decided stay the rules-only figures.
- The RAG's own score on the triggered questions is reported per trigger.

## Cost and time (estimates; no spend yet)

| Item | API | GPU machine |
|---|---|---|
| F1–F3 code and tests | none | none (fake backends) |
| v18 dev and dev2 re-parse (F4.1) | ~$0.85 (the v17 re-parse was $0.84) | none |
| Private run, rules only (F4.2) | ~$1.49 (range $1.19–1.93; `e2e_private.py estimate`, fallback off) | none |
| RAG merge (F4.3): judge the RAG's Natural QA answers and V2's rules answers | ~$0.7 (about 120 Natural QA gradings) | none (saved answers) |

Every paid step needs the owner's go-ahead on its estimate, behind the spend guard.

## Decisions (owner)

| # | Question | Draft answer |
|---|---|---|
| G1 | Which fallback: RAG only, RAG then Sonnet, or keep Sonnet | **Decided (owner, 2026-11-20): RAG only**, for the benchmark and the demo |
| G2 | Leakage-safe RAG or the RAG as it is | **Decided (owner, 2026-11-20): as it is**, with the README's run flags (owner to confirm they match the runs to keep) |
| G3 | Which triggers go to the RAG | **All of them** (`perception_failed`, `out_of_scope`, `parse_failed`, `program_cannot_run`, `unreadable_sign`, `uncertain`, `unknown`) |
| G4 | Should the scene graph be sent to the RAG | **No**: image and question only, the RAG's own design |
| G5 | The rule for choosing G1 on public_dev | **Not needed**: G1 is decided |
| G6 | The RAG's earlier private scoring | **Tune nothing on private**; the private run stays the final benchmark |
| G7 | Lift the holdout rule for one more paired run | **Not needed**: no fallback choice is left to make |
| G8 | Private run with the RAG live or precomputed | **Decided (owner, 2026-11-20): precomputed**, the saved deterministic answers (F4.3) |
