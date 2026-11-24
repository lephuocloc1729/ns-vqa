# Running SignCite with Docker Compose

## The services

| Service | What it is | Port |
|---|---|---|
| `web` | The UI (nginx). It is the one public entry point, and forwards `/v1`, `/health`, `/version` and `/docs` to `api`. | `WEB_PORT` (8080) |
| `api` | The backend API gateway and the rules pipeline (FastAPI, Python, SWI-Prolog). | internal only |
| `postgres` | Sessions, turns (answers, proofs, timings, cost) and feedback. | internal only |
| `prometheus` | Collects the API's `/metrics` and the server's CPU and RAM. | 127.0.0.1:9090 |
| `node-exporter` | The server's CPU, RAM, disk and network. | internal only |
| `grafana` | The dashboard "SignCite – hệ thống". | 127.0.0.1:3000 |
| `rag` | The RAG inference server. Opt-in profile `gpu`; needs an NVIDIA GPU. | internal only |

The services talk over Compose's internal network: REST from `web` to `api` and from `api` to `rag`, and SQL from `api` to `postgres`.

`/metrics` is not served to the public: Prometheus scrapes `api` directly. Prometheus and Grafana listen on 127.0.0.1 only. On a server, reach them through an SSH tunnel:

```bash
ssh -L 3000:localhost:3000 user@server
```

## A clean machine: no `.env`, no API key, no GPU

```bash
git clone https://github.com/lephuocloc1729/ns-vqa.git && cd ns-vqa
docker compose up -d --build
```

Then open:
- http://localhost:8080, the UI;
- http://localhost:3000, Grafana (`admin` / `admin`).

`api` runs the real API code with a **fake pipeline** (`VQA_PIPELINE=fake`):
- the same streaming, storage and metrics as the real one;
- fixed sample answers;
- no Claude calls.

The UI shows a red banner, so the fake is never mistaken for the real system. CI runs exactly this on every push (job `compose`), then checks one streamed answer and the monitoring.

Nothing depends on absolute paths or a personal environment. Every setting has a default in `docker-compose.yml`, and `.env.example` lists them all.

**The API image starts FROM the SignCite base image** (`ghcr.io/lephuocloc1729/signcite-base`, pinned by tag in `docker/api.Dockerfile`).
- It holds Ubuntu 24.04, Python 3.12 and SWI-Prolog 11.0.0, built by `.github/workflows/base-image.yml`, so building the API image never needs Launchpad.
- The package is private, like the repo. On a new machine, do one of:
  - `docker login ghcr.io` first, with a token that can read packages;
  - build the base locally under the same tag: `docker build -f docker/base.Dockerfile -t <the tag in api.Dockerfile> .` (this one step needs Launchpad);
  - have the owner make the `signcite-base` package public; it holds no project code.

## The real system (phase52 pipeline)

1. **`.env`** (gitignored; copy `.env.example`):

   | Setting | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | the key, put there by the owner |
   | `VQA_SPEND_LIMIT` | the spend cap agreed with the owner |
   | `POSTGRES_PASSWORD`, `GRAFANA_ADMIN_PASSWORD` | new values |
   | `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD` | a shared password for testers (optional) |

2. **The scene prompt's pictograms.** These are resized law_db figures under `prompts/scene/{v5,v5-crop,v5-tile}/pictograms/`, gitignored (the dataset-rule exception of 2026-11-15).
   - They are **never built into an image**: `.dockerignore` is a whitelist that leaves them out.
   - Copy them onto the machine that runs the stack only with the owner's agreement.
   - The API refuses to start in real mode without them, and the scene prompt refuses copies that don't match `pictograms.yaml`.

3. Start the stack:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.real.yml up -d --build
   ```

4. **The RAG fallback** (`VQA_ANSWER_FALLBACK=rag`). The RAG runs on a GPU machine (`docs/runbooks/gpu-session.md`). Point `VQA_RAG_URL` at it through an SSH tunnel; the RAG service is never exposed to the internet. On a machine with an NVIDIA GPU, use `--profile gpu` instead to start the `rag` service in the same stack.

## HTTPS on a server with a domain

`docker-compose.https.yml` puts Caddy in front of `web`. Caddy:
- serves the domain on ports 80 and 443;
- gets and renews the Let's Encrypt certificate by itself;
- redirects plain HTTP and `www.` to `https://` plus the domain.

Browsers allow the microphone and camera only over HTTPS.

1. Point the domain's A record (`@`, and `www` if wanted) at the server, and open ports 80 and 443.
2. Add to `.env`:

   ```bash
   DOMAIN=signcite.xyz
   WEB_PORT=127.0.0.1:8080          # the plain port, then reachable from the server only
   COMPOSE_FILE=docker-compose.yml:docker-compose.https.yml
   ```

   For the real pipeline, add `:docker-compose.real.yml` to `COMPOSE_FILE`.
3. `docker compose up -d --build`. The first certificate takes a few seconds once the domain resolves (`docker compose logs caddy`).

The `caddy_data` volume holds the certificates; keep it. CI runs the same overlay with `DOMAIN=localhost` (Caddy's own local CA) and streams one answer through it.

## Several questions at once

`VQA_ANSWER_SLOTS` (default 1) sets how many questions the API answers at the same time.
- The answers share one pipeline. Only its Prolog step (milliseconds) runs one at a time, and the Claude calls (about 20 s of each answer) overlap.
- More slots cost almost no memory.
- The ceiling is Anthropic's rate limits and the spend cap. The cap is safe: each call reserves its worst case first, so answers at once can't overspend.
- Why and how: `docs/plans/concurrent-answers.md`.

## Repeated RAG questions (`VQA_RAG_CACHE`)

With `VQA_ANSWER_FALLBACK=rag`, and `VQA_RAG_CACHE` on (the default; `off` disables it), a question the RAG has already answered (the same photo, the same words, the same RAG version) gets the RAG's earlier answer at once, without the GPU.

- **Why the answers are the same:** the RAG at one slot answers identically every time (`docs/results/rag-concurrency-2026-11-23.md`). The answer is still marked as a RAG answer, and its trace records `cache_hit`.
- **What is kept:** only successful answers given while the RAG runs one question at a time. Answers cached under one RAG version are never used for another.
- **When the GPU is off:** cached answers still serve, and new questions get the rules' answer.
- **Connecting the server to a rented GPU:** `docker/rag-session.sh on|off` with the `rag-tunnel` service (`docs/runbooks/gpu-session.md`).
- **Storage:** `var/rag_cache` in the `uploads` volume (a few KB per answer, at most 20,000; `VQA_RAG_CACHE_MAX_DAYS` can add an age limit).
- **Inspect or clear it** (for example before the UAT):

  ```bash
  docker compose exec api python -m app.api.rag_cache stats
  docker compose exec api python -m app.api.rag_cache clear
  ```

- **For the defense demo:** ask the demo questions once the day before, about your own photos.
- **Delete it after the defense.**

## The demo server

- A CloudNest VPS (Ubuntu 24.04, 2 vCPU, 4 GB RAM), domain `signcite.xyz`.
- The stack lives in `/opt/signcite`: the files of the deployed commit (named in `DEPLOYED_COMMIT`), its `.env` (root only) and the pictogram copies. CD keeps it up to date.
- The firewall (ufw) allows 22, 80 and 443.
- Grafana is reached through an SSH tunnel (above).

## The admin site (admin.signcite.xyz)

The plan is `docs/plans/admin-page.md`.

**What it has:**
- an overview with charts;
- the feedback inbox;
- every question, with its account;
- tester accounts;
- live settings.

**Setting it up:**
- **DNS:** an A record, `admin` → the server's IP. Caddy gets the certificate by itself.
- **`.env`:**
  - `ADMIN_PASSWORD` (and optionally `ADMIN_USER`, default `admin`);
  - `ADMIN_PORT` (default `127.0.0.1:8081`) also serves it on the server itself, e.g. through an SSH tunnel.
  - Without `ADMIN_PASSWORD` the admin site answers 404.
- **Two locks:**
  - nginx asks for the admin login on the admin site;
  - the API checks it again on every `/v1/admin` request.
  - On the public site, `/v1/admin` is 404.

**Tester accounts:**
- With `BASIC_AUTH_USER` and `BASIC_AUTH_PASSWORD` set, the public site's login accepts that shared account plus every enabled tester account made on the admin site.
- The API writes nginx's password file (apr1 hashes only) into the `siteauth` volume. nginx reads it on each request, so new, reset or locked accounts apply at once.
- Each question is stored with the account that asked. nginx sends it as `X-Remote-User`, overwriting anything a browser sends.

**GPU connection (Cài đặt → Máy GPU cho RAG):**
- Paste the GPU's SSH command, press **Nối**, then **Dùng RAG trên GPU này** once the RAG answers. **Ngắt GPU** switches the fallback off and disconnects.
- The `rag-tunnel` service runs all the time in standby and follows the target the API writes into the `gpu` volume (`docker/rag-tunnel/tunnel.sh`, `app/api/gpu.py`). The API never touches Docker or the SSH key.
- `docker/rag-session.sh on|off|status` does the same from the shell (`docs/runbooks/gpu-session.md`).

**CSV export:** Câu hỏi and Phản hồi each have **Tải CSV**, with the current filters (UTF-8 with a BOM, so spreadsheet apps read the Vietnamese text).

**Live settings:**
- The RAG fallback, the RAG URL, the RAG cache switch, the spend limit and the follow-up switch can change while the API runs: on the admin site, or with `docker compose exec -T api python -m app.api.live show|set KEY=VALUE|reset`.
- They apply from the next question. The `.env` values are the defaults.
- Switching to the RAG is refused unless it answers `/health`.

## Follow-up questions (`VQA_FOLLOWUP`)

Neither the rules pipeline nor the RAG keeps a conversation: each answers one complete question about one photo. So the API rewrites a follow-up such as "Còn xe khách thì sao?" into a complete question before it is queued (`app/api/followup.py`, prompt `prompts/followup/v1/spec.md`):

- only with a `session_id`, and only when the session already has a question about the same photo; the first question about a photo makes no call;
- one Claude Haiku call (about $0.0005), counted by the same spend guard, made before the answer slots, so it never holds one;
- the asker's words are stored as `question`, the rewritten one as `understood_as`, and the page shows "Hiểu câu hỏi là: …";
- a question that is already complete passes unchanged; any failure answers the question as typed;
- on by default; `VQA_FOLLOWUP=off` in `.env`, or the live switch (Cài đặt → Câu hỏi tiếp), turns it off;
- the metric `vqa_followup_total{result}` counts rewritten, unchanged, failed and rejected rewrites.

## CD: every merge to `main` deploys itself

`.github/workflows/cd.yml` runs after CI passes on a push to `main` (or by hand: Actions › CD › Run workflow).

1. **Build:** the `api` and `web` images, pushed to GHCR as `ghcr.io/<owner>/signcite-{api,web}:<commit>` and `:latest`.
2. **Deploy:** sends the commit's files (`git archive`) to the server over SSH, logs the server in to GHCR with the run's short-lived token, runs the commit's own `docker/deploy.sh`, then logs out.
3. **`docker/deploy.sh` on the server:**
   - pulls the new images (if the registry fails, nothing has changed yet);
   - saves the files the commit replaces, notes the ones it adds, unpacks the commit's files (`.env` and the pictogram copies are not in git, so they stay), records the images in `.env` (`API_IMAGE`, `WEB_IMAGE`) and restarts what changed;
   - checks the stack: the containers are healthy, the API's `/health` reports the database, and `https://DOMAIN/healthz` answers;
   - if the check fails, it puts back the previous files and images, removes the files the commit added, checks again and fails the run.
4. **Check:** GitHub confirms the public site answers.

Each run shows as a `production` deployment on the repository's Deployments page.

**Secrets** (repository settings › Secrets and variables › Actions):
- `DEPLOY_HOST`: the server's address.
- `DEPLOY_SSH_KEY`: a key used only by CD, its public half in the server's `authorized_keys` (comment `github-actions-cd signcite`).
- `DEPLOY_KNOWN_HOSTS`: the server's host keys (`ssh-keyscan <host>`), so the runner never trusts an unknown host.

**Tested (2026-11-22):**
- **A merge deploys itself:** PRs #15 and #16 each ran CI → build → GHCR → deploy → checks.
- **A broken build rolls back by itself:** a `web` whose `/healthz` gives 503, deployed through CD by hand (Run workflow), failed its check and was rolled back. The run turned red; the site gave errors for about 90 s, then served the previous version.
- **Files are restored on rollback:** by hand on the server, the replaced files came back and an added file was removed.
- **The registry is unreachable** (an image tag that doesn't exist): the pull fails before anything changes. `.env`, the files and the running containers stay as they were.
- **A server reboot:** the site answered again after 25 s. All 7 services came back (restart policy `unless-stopped`; Docker, containerd and ufw start at boot). The database kept its rows, Caddy reused its stored certificates, and only 22, 80 and 443 answer from outside.

**Roll back by hand:** set `API_IMAGE` and `WEB_IMAGE` in `.env` to an earlier commit's tags and run `docker compose up -d`.

## Data and backups

Named volumes hold the state: `pgdata`, `uploads`, `scenes`, `apilogs`, `promdata` and `grafdata`.
- `docker compose down` keeps them.
- `docker compose down -v` deletes them.

Back up the database:

```bash
docker compose exec postgres pg_dump -U vqa vqa > backup.sql
```
