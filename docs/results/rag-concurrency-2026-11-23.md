# RAG on one RTX 5090: how many questions at once, 2026-11-23

**Setup:**
- **Machine:** one rented RTX 5090 (32 GB) on vast.ai, image `ghcr.io/lephuocloc1729/ns-vqa-rag:latest`.
- **Code:** the settings of PR #22 copied on.
- **Service:** configuration `rag-c@ac78ebff0dcf`. Two llama.cpp servers with Qwen3.5-9B Q4_K_M (caption and answer, both with the image projector), plus the F2LLM-v2 0.6B embedder.
- **Benchmark:** `eval/rag_bench.py`, from the Mac through an SSH tunnel. 24 public_dev questions on 21 photos, after 2 untimed warm-up questions.
  - C requests in flight with `RAG_WORKERS = RAG_LLAMA_PARALLEL = C`.
  - Each llama slot keeps the full context (caption 16K, answer 64K) except where noted.
  - GPU memory and use come from `nvidia-smi` every 2 s.

## Results

| slots (= requests at once) | answers/min | time per answer, mean (p50 / p95) | caption / answer stage | peak VRAM | GPU busy | answers identical to 1 slot |
|---:|---:|---|---|---:|---:|---:|
| **1** (the benchmarked setup) | **6.8** | **8.6 s** (7.7 / 20.7) | 3.4 s / 5.2 s | 18.7 GB | 57% | 24/24 on a rerun |
| 2 | 11.6 (1.7×) | 9.6 s (9.5 / 15.7) | 3.5 s / 6.1 s | 21.4 GB | 74% | 6/24 |
| 4 | 13.0 (1.9×) | 16.7 s (13.8 / 22.4) | 7.9 s / 8.8 s | 26.8 GB | 80% | 5/24 |
| 8 (32K per slot) | — | — | — | 32.0 GB at rest | — | **all 24 failed: CUDA out of memory** |

- **Memory:** 17.7 GB at rest with 1 slot, 20.4 GB with 2, 25.7 GB with 4.
- **8 slots do not fit**, even with the answer slots cut to 32K. The two llama-servers took the card, and the embedder (PyTorch) could not allocate.
- **The largest prompt was 26.7K tokens.** Answer slots smaller than about 32K would make the longest questions fail.

## What it shows

1. **One question at a time is the benchmarked and reproducible setup.** A rerun gave the same answers for all 24 questions (temperature 0, seed 2025).
2. **More slots raise throughput a little and change the answers.**
   - 2 slots give 1.7× the answers per minute at about +1 s per answer.
   - 4 slots give 1.9×, but each answer takes twice as long.
   - The GPU is near saturation at 2–4 slots.
   - With batching, llama.cpp computes in a different order, so only 5–6 of 24 answers stay word-for-word the same (about 78% similar text on average). The RAG with several slots is therefore **not** the system whose accuracy the thesis reports (V2, RAG alone). Its accuracy would have to be measured again.
3. **The limit on one 5090 is 4 at once.** 8 does not fit in 32 GB.

## For the demo and the report

- **Keep 1 slot:** 6.8 fallback answers a minute, the answers of the benchmarked V2.
  - With the API's 10 answer slots, at most 19–33% of questions go to the RAG. At normal use that is well under 6.8 a minute.
  - Under sustained full load, the API ships the rules' answer after `VQA_RAG_TIMEOUT_S`.
- **To report:** *the RAG answers one question at a time on one RTX 5090 (6.8 a minute, 8.6 s each, 18.7 GB).*
  - *Two model slots would raise that to 11.6 a minute (1.7×), and four to 13.0 (1.9×, 26.8 GB).*
  - *Batching changes the generated text, so the evaluated system keeps one slot.*
  - *Eight slots exceed 32 GB.*
