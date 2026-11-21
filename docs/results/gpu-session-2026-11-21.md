# GPU session, 2026-11-21: RAG service setup, equivalence, Q4 vs BF16, end to end

**Machine:** vast.ai, 1× RTX 5090 (32 GB), driver 580.178.04, Hugging Face download about 26 MB/s per connection.

**Software:**
- image `ghcr.io/lephuocloc1729/ns-vqa-rag@sha256:2b8aa1ea…` (main `0009e0f`): torch 2.14.1+cu130, llama.cpp b11624;
- RAG service `rag-c@ac78ebff0dcf`;
- assets from bundle `e1811fa3…` (no private-test files);
- public-test questions only.

**Outputs:** gitignored in `services/rag/evidence/gpu-2026-11-21/`.

## 1. Setup time (fresh machine)

| Step | Time |
|---|---|
| Qwen3.5-9B Q4_K_M + mmproj (6.2 GB, sha256-checked), 16 parallel connections | about 1 min (about 95 MB/s) |
| `gpu_setup.sh`: bundle (hash-checked), 1,446 files checked, weights, llama.cpp; packages already in the image | 17 s |
| Service start: train bank, f2llm encoder, two warm llama-servers | 55 s (15–20 s on a restart) |

The first session (rsync from the Mac, pip install) took about 45 minutes.

## 2. Service vs the batch runner's live pipeline (20 public questions, `public_natural_0001`–`0020`)

The batch pipeline is the one the live private run used (`run_private_live.sh`): live captions, embeddings in batches of 8, then retrieval and answer.

**End to end, service vs batch:** gate identical on 20/20. Cited laws identical on 13/20, retrieved lists on 12/20, few-shots on 16/20, answer text on 4/20.

**Stage by stage, the service's code given the batch's inputs:**

| Stage | Identical |
|---|---|
| Live captions (fresh caption server, same order) | **20/20** |
| Query representations | **20/20** |
| Retrieval, given the batch's vectors | **20/20** |
| Answers, given the batch's exact inputs (fresh answer server, same order) | **20/20** |
| Query embeddings: one question at a time (service) vs batches of 8 (batch) | differ: max abs 1.6e-2, median 9.1e-3; re-batching the same 8 reproduces the batch's vectors exactly |

**Reading:**
- The service reproduces the pipeline exactly except for one numerical effect: f2llm in BF16 gives slightly different vectors for a padded batch than for a single text.
- Those vectors change some retrieval scores, and the scores appear in the answer prompt ("[Hạng 1; điểm …]"). So the answer text changes even where the retrieved laws are the same.
- Neither form is wrong: a batch-of-8 vector depends on which questions share the batch.
- The benchmark figures come from the batch runs. The service is the deployed form.

**Determinism:** the answer step, re-run with the same inputs on a fresh server, gave identical answers on 20/20.

## 3. Latency of the service (warm, 20 public questions)

| Stage | Mean | p50 | Max |
|---|---|---|---|
| Caption | 3.79 s | 2.33 s | 19.85 s |
| Embedding | 0.05 s | 0.02 s | 0.73 s |
| Retrieval | 0.01 s | 0.01 s | 0.01 s |
| Answer | 4.89 s | 4.58 s | 9.09 s |
| **Total** | **8.74 s** | **6.75 s** | **23.38 s** |

**Peak GPU memory, service:** 18.4 GB (caption server 7.3 GB, answer server 9.3 GB, encoder 1.8 GB).

**Streaming vs plain** (after the UTF-8 fix, `99e7d4d`): answer, analysis and citations identical; the streamed tokens join up to `final_answer`.

## 4. Q4_K_M vs BF16 answer model (same 20 questions, same live captions and embeddings)

| | **Q4_K_M** | BF16 |
|---|---|---|
| Model file | 5.68 GB | 17.92 GB |
| Peak GPU memory (answer server) | **9.29 GB** | 19.61 GB |
| Generation | **4.9 ms/token (203 tokens/s)** | 11.0 ms/token (91 tokens/s) |
| Prompt processing | **7,110 tokens/s** | 5,696 tokens/s |
| Time per answer | **4.82 s** mean (p50 4.29, max 9.05) | 6.48 s mean (p50 6.02, max 10.93) |
| Output tokens | 196 mean | 207 mean |
| Same answer text as the other model | 1/20 | 1/20 |

- Q4 uses 53% less GPU memory and generates 2.2× faster; each answer takes about 26% less time.
- **Accuracy is not measured here.** The two models phrase answers differently. Accuracy comes from grading the saved private Q4 and BF16 runs, separately.

## 5. End to end: ns-vqa API (phase52, `VQA_ANSWER_FALLBACK=rag`) → SSH tunnel → RAG service

| Question | Gold | Route | Answer | Claude cost | Time |
|---|---|---|---|---|---|
| `0005` (13-sign gantry; engine verdict unknown) | Đúng | **RAG fallback**, basis `[fallback, rag]`, 6 RAG laws in `retrieved`, no rule citations | "Đúng, hàng đường ở phía bên tay trái chỉ dành cho xe ô tô, …" | $0.0693 (the first parse writes the parser's prompt cache) | 25.5 s |
| `0055` (guide sign, direction) | Đúng | rules (guide reading), cites E.14 | "Đúng. Biển chỉ hướng đi đến Thành phố Vinh là hướng đi thẳng." | $0.0073 | 15.2 s |
| `0063` (guide sign, roundabout) | Đúng | rules, cites C.6, `reading_choice` | "Đúng. Biển W.206 (Giao nhau chạy theo vòng xuyến) cho thấy nút giao này là vòng xuyến." | $0.0090 | 24.5 s |

- **All three are right.** The streamed tokens join up to each answer.
- **Total Claude spend for this step:** $0.0855.
- **For the UI:** the RAG's `final_answer` is its last JSON field, so its tokens arrive in the last ~0.2 s of an 18 s RAG answer. Showing the RAG's own stage events (caption, retrieval) during that wait would help the user.

## Bugs found and fixed in this session

- **`99e7d4d`:** streamed RAG answers were garbled (UTF-8 read as Latin-1, because llama-server sends no charset). The service now decodes UTF-8 itself, and the test sends raw UTF-8.
- **`8aee2ff`:** `fetch.py` briefly needed twice a file's size on disk, which filled the 40 GB disk while downloading BF16. It now downloads in place, and resuming works.
