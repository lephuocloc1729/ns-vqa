# GPU session runbook (RAG service)

Goal: a rented GPU running the RAG service in about 10 minutes, with nothing uploaded from the Mac at GPU time.

## Once, on the Mac

1. On huggingface.co, create a **private** dataset repo, e.g. `<hf-user>/ns-vqa-rag-assets`.
2. Log in with your own token:
   ```bash
   hf auth login
   ```
3. Build and upload the bundle (109 MB; no private-test files).
   ```bash
   cd services/rag && python3 scripts/make_bundle.py
   ```
   ```bash
   RAG_ASSETS_REPO=<hf-user>/ns-vqa-rag-assets bash scripts/upload_bundle.sh
   ```
   The upload script refuses a repo that is public.

The GPU image `ghcr.io/lephuocloc1729/ns-vqa-rag:latest` is built by GitHub Actions on every merge to `main` that touches `services/rag/`.

## Each session

1. **Rent:** on vast.ai, filter for an RTX 4090/5090 (or any ≥ 24 GB), **download ≥ 500 Mbps**, and ≥ 40 GB disk.
2. **Image:**
   - Use `ghcr.io/lephuocloc1729/ns-vqa-rag:latest`, launch mode "SSH".
   - The package is private while the repo is private. Either make the package public (it holds code only, no data), or give vast.ai registry login with a GitHub token that has `read:packages`.
   - Without the image: use any CUDA PyTorch template, `git clone` this repo, and run the same setup command. It installs the packages with `uv` (a few minutes).
3. **Set up,** in `/app` in the image, or in `services/rag` in a clone. Log in to Hugging Face first:
   ```bash
   hf auth login
   ```
   Then run the setup with the repo name:
   ```bash
   RAG_ASSETS_REPO=<hf-user>/ns-vqa-rag-assets bash scripts/gpu_setup.sh
   ```
   Add `--bf16` only for the Q4 vs BF16 measurement (17.9 GB more).
4. **Start the service:**
   ```bash
   uvicorn --factory text_based_rag.service_api:create_app --host 0.0.0.0 --port 8100
   ```
   Check it:
   ```bash
   curl localhost:8100/health
   ```
5. **Use it from the Mac:** `ssh -p <port> root@<host> -L 8100:localhost:8100`. Then run the ns-vqa API with `VQA_ANSWER_FALLBACK=rag VQA_RAG_URL=http://127.0.0.1:8100`.
6. **After:**
   - **Stop** the instance if the next session is soon: its disk is kept. A restart can wait if someone else has rented that GPU.
   - **Destroy** it otherwise: that deletes everything on it.

## What the session checks (plan S6-D)

- The service against the batch runner's live pipeline (`experiments/latency/run_live.sh`) on the same public questions: answers and retrievals identical.
- Streaming against non-streaming: the same answers.
- Latency per stage and peak VRAM for the thesis; then Q4 vs BF16.
- 2–3 undecided questions end to end through the ns-vqa API (about $0.02 of Claude for the rules side).
