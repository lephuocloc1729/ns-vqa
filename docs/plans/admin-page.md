# Plan: the admin site (approved by the owner, 2026-11-23)

The admin site is the Review 3 checklist item 1.3 "dashboard page with charts". Settings can be changed live, and testers have their own accounts.
- **PR 1:** before the UAT (first session on 2026-11-26).
- **PR 2:** after it, GPU connect/disconnect from the page.

## Where it lives

- **https://admin.signcite.xyz**
  - Its own password: `ADMIN_USER` / `ADMIN_PASSWORD` in the server's `.env`.
  - Checked twice: by nginx, and again by the API on every `/v1/admin/...` request.
  - With no `ADMIN_PASSWORD`, the admin site is off.
- **On the public site,** `signcite.xyz/v1/admin/...` returns 404 in nginx.
- **DNS:** the owner adds an A record, `admin` → the server's IP. Caddy gets the certificate.
- **Locally:** the admin site is served on `ADMIN_PORT` (default 8081, on 127.0.0.1 only).

## What it shows (PR 1)

1. **Overview,** for a date range.
   - **Cards:** questions, conversations, testers; the route mix (rules, fallback, RAG cache, not decided); the 👍 share; p50/p95 seconds; cost, with the spend guard's spent amount and limit; errors.
   - **Charts:** questions per day, the verdict mix, routes per day, a seconds histogram, cost per day.
   - Simple SVG; no chart library.
2. **Feedback:** answers rated 👎 or corrected. Each shows the photo, the question, the answer, the correction and the note.
3. **Questions:** recent questions, filtered by route, verdict, rating, status and account. One opens in the same view the user saw.
4. **Accounts:** one site account per tester.
   - Create one with a generated password, shown once.
   - Reset the password; disable and enable; see the last question and the question count.
5. **Settings,** applied from the next question on, with no restart:
   - **RAG fallback:** off, rag or claude.
     - Switching to rag first checks that the RAG answers at its URL, and refuses with the reason if not.
   - **RAG answer cache:** on or off. A button clears it, after confirmation.
   - **The spend limit,** for this API process.
   - **Reset to the `.env` defaults.**

## How it works

- **Live settings:** an `app_setting` table holds overrides of the `.env` values.
  - The API reads it before each question.
  - When something changed, it swaps the pipeline's fallback object and config. Only `app/` code is involved; `vqa/` is unchanged.
  - Questions already running finish with what they started with.
  - The answer slots, the pipeline profile, passwords and keys stay in `.env`.
- **`rag-session.sh`:** `on` and `off` set the fallback through the same table (`python -m app.api.live`), so they no longer restart the API.
- **Tester accounts:**
  - The `site_account` table stores apr1 hashes, a format nginx reads itself, never plain text.
  - The API writes nginx's password file to a volume that both containers share. It holds the `.env` shared account plus every enabled tester account.
  - nginx reads the file on each request, so changes apply at once.
- **Who asked:** nginx passes the logged-in name to the API as `X-Remote-User`, overwriting anything the browser sent. Each question is stored with its account.
- **Leakage guard:** the admin site only reads stored answers and feedback. The pipeline never reads them.

## PR 2 (2026-11-24, owner: "complete the admin console")

- **GPU connect/disconnect on Cài đặt.**
  - `rag-tunnel` runs all the time and follows a target file in a shared volume (`docker/rag-tunnel/tunnel.sh`).
  - The API writes the target and reads the state (`app/api/gpu.py`, `/v1/admin/gpu`). It never touches Docker or the key.
  - "Ngắt GPU" switches the fallback off before disconnecting. `rag-session.sh` uses the same target.
- **CSV export** of Câu hỏi and Phản hồi (`/v1/admin/turns.csv`, `/v1/admin/feedback.csv`).
- **The forward now goes to `127.0.0.1:8100` on the GPU,** not `localhost`, which can resolve to IPv6 first while the RAG listens on IPv4.

## Not in PR 1 or 2
- CSV export.
- Deleting data from the page.
- A full in-app login system.
