# GPU session runbook (RAG service)

Goal: a rented GPU running the RAG service a few minutes after it boots, with nothing to type on the machine and nothing uploaded from the Mac. Measured on 2026-11-21: about 2–3 minutes (see `docs/results/gpu-session-2026-11-21.md`).

## Once

1. **On huggingface.co:**
   - Create the **private** dataset repo `lephuocloc/ns-vqa-rag-assets` (done).
   - Upload the bundle from the Mac with a write token (done; `scripts/make_bundle.py`, then `scripts/upload_bundle.sh`).
2. **Create a read-only token for GPU machines:** Settings → Access Tokens → Create new token.
   - **Fine-grained,** with only *read* access to `lephuocloc/ns-vqa-rag-assets`.
   - **Name:** `vast-gpu`.
3. **Create a vast.ai template:** Templates → New.

   | Field | Value |
   |---|---|
   | Image | `ghcr.io/lephuocloc1729/ns-vqa-rag:latest` (the package is public: code only) |
   | Launch mode | SSH |
   | Docker options | `-p 8100:8100 -e HF_TOKEN=<the read-only token>` |
   | On-start script | `bash /app/scripts/onstart.sh` |
   | Disk | 40 GB, or 60 GB to also run BF16 (then add `-e RAG_SETUP_ARGS=--bf16`) |

   - vast.ai can also keep the token as an account-level environment variable (Account → Environment Variables), instead of in the template.
   - The token stays in vast.ai, never in this repo. Revoke it on Hugging Face if it ever leaks.

The image is rebuilt by GitHub Actions on every merge to `main` that touches `services/rag/`.

## Each session

1. **Rent:**
   - Search with the template selected;
   - **RTX 4090/5090** (≥ 24 GB), **Inet down ≥ 500 Mbps**, reliability ≥ 98%.
2. **Wait:** the on-start script runs by itself.
   - It pulls the weights and the bundle (checking every hash), then starts the service.
   - Progress is in `/app/logs/onstart.log`.
3. **Connect from the Mac** with the vast.ai key, forwarding the service:
   ```bash
   ssh -i ~/.ssh/vast_gpu_ed25519 -p <port> root@<host> -L 8100:localhost:8100 -N
   ```
   Then check it:
   ```bash
   curl localhost:8100/health
   ```
   `{"status":"ok"}` means ready.
4. **Use it:** run the ns-vqa API with `VQA_ANSWER_FALLBACK=rag VQA_RAG_URL=http://127.0.0.1:8100`.
5. **After:** **destroy** the instance in vast.ai. Everything on it can be recreated. "Stop" keeps the disk, but a restart waits if someone else has rented that GPU.

**By hand, if the on-start script is not set:** in `/app`, run `bash scripts/gpu_setup.sh`, then start the service:
```bash
uvicorn --factory text_based_rag.service_api:create_app --host 0.0.0.0 --port 8100
```
`gpu_setup.sh` reads `HF_TOKEN` from the container's environment even when the SSH shell lacks it. Without a token it stops with a clear message, and then `hf auth login` on the machine also works.

**Without the image:** use a CUDA PyTorch template, `git clone` the repo, `cd services/rag`, and run the same two commands. Packages then install with `uv` (a few minutes).

## Connect the demo server (signcite.xyz) to the GPU

The server reaches the RAG through the `rag-tunnel` service: one SSH connection from the server to the GPU, forwarding the RAG's port to the stack's internal network only. Nothing is published on the server, and the vast.ai key never leaves the Mac.

**Once:**
- On the server: `cd /opt/signcite && bash docker/rag-session.sh key`. This makes the server's own key (`secrets/rag_tunnel_ed25519`, root only) and prints its public half.
- Add that public key in vast.ai under **Account › SSH keys**, so every rented machine accepts it.

**Each session:**
1. Rent the GPU as above, and wait until its `curl localhost:8100/health` says ok.
2. On the server:

   ```bash
   cd /opt/signcite && bash docker/rag-session.sh on <host> <port>
   ```

   Use the GPU's SSH host and port, as vast.ai shows them. The script:
   - starts the tunnel and waits for the RAG to answer through it;
   - sets `VQA_ANSWER_FALLBACK=rag` and `VQA_RAG_URL=http://rag-tunnel:8100`;
   - restarts the API and prints both `/version`s.

   The RAG answer cache is on by itself.
3. Check on signcite.xyz:
   - an undecided question gets a RAG answer (the "Trả lời bằng RAG" badge, with laws);
   - the same question again is instant, and its turn has `stages.fallback.cache_hit: true`.

   `bash docker/rag-session.sh status` shows the state.
4. **Before destroying the GPU:** `bash docker/rag-session.sh off`. The fallback goes back to off and the tunnel stops.
   - CD never waits for the tunnel, so a forgotten `off` cannot block a deploy.
   - But undecided questions would try a RAG that is gone, until `off` is run.

## What a session downloads (2026-11-23)

- **`rag_bundle`, every session:** what the RAG service needs, and **no test-split file**.
  - The law corpus and its index; the train captions, embeddings and images; the law files.
  - The service's caption settings now sit beside its code (`services/rag/src/text_based_rag/caption_settings.json`), so it reads no test file.
- **`rag_eval_bundle`, only on request** (`RAG_SETUP_ARGS=--eval`, or `bash scripts/gpu_setup.sh --eval`): the public-test caches and data. Evaluation runs of the batch runner (`--split public_test`) and the checks below need it.
- **No private-test file** is in either bundle.
- **Rebuild and upload both** after changing the assets:

  ```bash
  python scripts/make_bundle.py && bash scripts/upload_bundle.sh
  ```

  Do it only once the GPU image with the matching scripts is on GHCR (it builds when `services/rag/` changes on `main`).

## Checks a session can run (plan S6-D; done 2026-11-21; these need `--eval`)

- **The service against the batch runner's live pipeline,** on the same public questions. Stage by stage it matches; the only difference is the query-embedding batch size.
- **Streaming against non-streaming:** the same answers.
- **Speed and memory for the thesis:** latency per stage and peak VRAM; Q4 vs BF16.
- **End to end:** undecided questions through the ns-vqa API.
