# SignCite UAT: moderator notes

These notes are for the person who runs the sessions. Testers get `task_sheet.md` one task at a time, then the form (`form_questions.md`). Results are scored by `score_sus.py` and `turn_stats.py`, then written up in `report_template.md`.

**The plan:**
- **Testers:** at least 15, ideally 20.
  - A mix of drivers, students, and **2–3 people who know traffic law**.
  - **About half on phones.**
- **Each tester:** 5 fixed tasks, then 2 questions on one new photo, then the form. That takes about 20–25 minutes.

## Acceptance targets (owner, 2026-11-23)

These are fixed before the first session and are not changed afterwards. `score_sus.py` prints each one with pass or fail.

| Target | Meaning |
|---|---|
| Mean SUS ≥ 68 | easier to use than the average product (68 = the average across published studies) |
| Task success ≥ 80% | of all fixed-task attempts, counting only full successes |
| CSAT 4–5 ≥ 70% | of testers say they are satisfied or very satisfied |
| Every task ≥ 60% | no single feature fails for more than 4 testers in 10 |

**If a target is missed,** report it with its cause (issue tags, notes) and a fix, or say why it can't be fixed. Never re-run sessions to improve a number.

## 1. Before the first session (once)

### Photos

You need about **20**, all taken by you on the street. **Never use dataset photos:** testers would see train or test images, and the pipeline has seen most train scenes.

**Fixed-task photos: 3 used, plus 2 backups.**

| Photo | Used in | What it must show |
|---|---|---|
| Ảnh 1 | T1, T5 | one clear sign, any kind |
| Ảnh 2 | T2, T3 | a ban that treats cars and motorbikes differently, e.g. P.103a "cấm ô tô" (car: no; motorbike: yes) |
| Ảnh 3 | T4 | a speed limit (a number in a red circle, P.127) |
| 2 backups | — | another Ảnh 2-type and another Ảnh 3-type photo, in case the dry run fails on one |

**Spare photos for the free questions: 15 (Ảnh 6 to Ảnh 20), plus 3–5 extra if easy.** Testers without a street photo of their own get one each. Mix them:

| How many | What |
|---|---|
| ~5 | a ban or mandatory sign with an extra plate (times, vehicle types, weight) |
| ~3 | several signs on one pole or one gantry |
| ~2 | a speed limit with lanes, or a lane board |
| ~2 | warning or information signs |
| ~3 | hard ones: far away, at an angle, partly hidden, faded, or a local plate with text |

**Rules for every photo:**
- daylight;
- the sign at least about 80 px tall;
- no readable faces or number plates;
- JPEG or PNG under 10 MB.

**Rules for the spare photos:**
- **Never ask SignCite about a spare photo before its session.** The first question on a photo caches its scene. A tester's first question must be the real first one, because that is where the report gets the real wait.
- **One spare photo per tester, never reused.**
- Record who got which in `eval/runs/uat/photos_used.csv`, with the columns `participant,photo` (e.g. `P03,Ảnh 9`). For unmoderated sessions, assign them in advance by ID: P01 gets Ảnh 6, P02 gets Ảnh 7, and so on.
- You can check the hard ones by eye. Don't run them.

**Sending photos to testers:**
- Use a Google Drive folder or a zip file.
- Don't use Zalo or Messenger: they re-compress photos. A re-compressed fixed photo is a different file, so the dry run's cache wouldn't apply to it.

### Dry run (fixed photos only)

**Cost:** about $0.10, with the owner's go-ahead first.

- Ask each fixed task's question once on signcite.xyz. Write down the expected answer, the sign code and the cited article.
- **If an answer is wrong or undecided, switch to the backup photo,** not a different task. The fixed tasks test the interface, not the model.
- The dry run caches these photos, so T1–T4 answers will be faster than a first question on a new photo. `turn_stats.py` reports the two kinds separately.

| Task | Question | Expected answer | Sign | Article |
|---|---|---|---|---|
| T1 | Biển báo này có nghĩa là gì? | | | |
| T2 | Xe ô tô con có được đi vào đường này không? | | | |
| T3 | Xe máy có được đi vào không? | | | |
| T4 | Tốc độ tối đa cho phép ở đây là bao nhiêu? | | | |

### Other preparation

- **Participant IDs and accounts:** `P01`, `P02`, … in the order people book.
  - On admin.signcite.xyz → Tài khoản, create the account `p01`, `p02`, … for each one. The password shows once; send it privately.
  - Every question that tester asks is then stored with their account, so the admin site's Câu hỏi tab (filter by account) and the report can link the form, your log and what they actually asked.
  - After the UAT, press **Khoá tất cả** to lock every tester account.
- **The form:**
  1. Submit one dummy response.
  2. Download the CSV and run `score_sus.py` on it.
  3. Delete the dummy response.
- **Form settings:** emails not collected; not limited to one response.
- **The spend cap** (owner's decision):
  - Expect about 20 testers × ~6 questions × $0.015 ≈ $2, plus retries.
  - Set `VQA_SPEND_LIMIT` in the server's `.env`, then restart the API before each session day, since the cap counts from a restart.

## 2. Each session day (the server)

**Before the first tester:**
1. Rent the GPU. On admin.signcite.xyz → Cài đặt → Máy GPU cho RAG, paste its SSH command, press **Nối**, then **Dùng RAG trên GPU này**. Or run `bash docker/rag-session.sh on <host> <port>` on the server (`docs/runbooks/gpu-session.md`).
2. Check on admin.signcite.xyz → Cài đặt (or `/version`): the fallback is RAG and reachable, there are 10 answer slots, the RAG cache is on, and **Câu hỏi tiếp** (follow-up questions) is on.
3. Write down the start time in UTC, for `turn_stats.py`.
4. Ask one question on a **fixed** photo to warm everything up. Never use a spare photo for this.

**After the last tester:**
1. Press **Ngắt GPU** on the admin site (or run `bash docker/rag-session.sh off`), then destroy the GPU.
2. Write down the end time.

**If the RAG or GPU goes down mid-session:**
- Answers the rules can't decide show "Hệ luật chưa quyết định được…". Testing continues.
- Tag the attempt `fallback_off` and note the time.

## 3. Running a session

**Formats:**
- **In person, or a video call with screen sharing (preferred):** you fill in the observation log.
- **Unmoderated:** the tester gets the tasks and the form only. The form's `[OK1]`–`[OK5]` answers stand in for the log, and the report must call those rates **self-reported**.

**Introduction (in your own words):**
1. *"Cảm ơn bạn. Hôm nay mình thử phần mềm, không thử bạn. Không có câu trả lời sai."*
2. *"Bạn vừa làm vừa nói to suy nghĩ nhé: đang tìm gì, mong đợi gì, thấy lạ chỗ nào."*
3. *"Mình sẽ không giúp trong lúc làm, vì mình muốn biết phần mềm tự nó có rõ không. Bí quá 3 phút thì mình chuyển nhiệm vụ."*
4. Check they can log in with their own account (sent privately, never in a group chat). Then give them Ảnh 1–3.

**Handing out tasks:**
- **One task at a time,** on a card, a slide, or pasted into the call's chat.
- The tester reads it aloud. **Start the timer when they finish reading.**
- **Don't explain further, and never use the app's button names.**
  - The wording deliberately avoids words such as "Căn cứ và chứng minh", "khung biển báo", "Lịch sử" or "Sửa đáp án".
  - If asked *"bấm vào đâu?"*, answer *"Bạn nghĩ nên làm gì?"*.
- After 3 minutes on one task, mark it `fail` and move on.
- **Stop the timer** when the tester says the result aloud. Every task ends with "→ say it to the moderator".

**Outcomes:**
- `success`: the result is said without help.
- `partial`: half the result, or the whole result after one hint. Examples:
  - T2: the verdict but not the article;
  - T3: the answer, but the photo was re-attached or a new chat was opened;
  - T4: typed instead of spoken.
- `fail`: otherwise, or the tester gave up.

**What each task needs:**

| Task | Success needs | What to watch |
|---|---|---|
| T1 | the sign's meaning, said aloud | finding attach; reaction to the wait |
| T2 | the verdict **and** the law and article (they are folded under the answer) | do they find and open the folded part? |
| T3 | the motorbike answer **and** pointing to the right sign on the photo | do they re-attach the photo? a short follow-up ("Còn xe máy thì sao?") is fine: check the "Hiểu câu hỏi là: …" line under it says what they meant; do they find the photo with the boxes? |
| T4 | the question recognised from speech, and the answer said | the microphone permission, recognition errors; note the browser and device |
| T5 | the T1 chat reopened **and** a rating sent (the thanks message appears) | on a phone, finding the history; understanding the icon buttons |

**The answer being *legally wrong* is not a task failure.** Tag it `answer_wrong` and write what was asked.

**The 2 free questions (not timed or scored as tasks):**
- If the tester has no street photo, give them the next unused spare photo and record it in `photos_used.csv`.
- Phone testers should take the photo with the app's camera if they can.

**Afterwards (2 minutes):**
- Ask *"Điều gì làm bạn khó chịu nhất?"* and *"Bạn có tin câu trả lời không? Vì sao?"*
- Write the answers in `notes`, then send the form link.

## 4. The observation log

- **Where:** upload `observation_log_template.xlsx` to Google Drive and open it with Google Sheets.
  - It has rows ready for P01–P20 × T1–T5, an outcome dropdown and a `photos_used` tab. Untouched rows are skipped when scoring.
  - Afterwards, use File › Download › CSV for the `observations` tab and the `photos_used` tab, and save them as `eval/runs/uat/observations.csv` and `photos_used.csv`. That folder is gitignored, so the log never gets committed.
  - `observation_log_template.csv` is the same format as plain text.
- **Rows:** one per participant and task.
  - `participant`: P01…
  - `task`: T1–T5
  - `outcome`: `success`, `partial` or `fail`
  - `time_s`: seconds
  - `issues`: tags separated by `;`
  - `notes`: free text, with no names
- **Use these tags** so they can be counted. Add a new one only if none fits:

| Tag | When |
|---|---|
| `waiting_too_long` | complains about or visibly struggles with the wait |
| `upload_hard` | couldn't find or use attach, drag-drop or camera |
| `voice_failed` | the microphone, permission or recognition didn't work |
| `answer_wrong` | the tester (or you) judged the answer legally wrong |
| `answer_unclear` | the answer was hard to understand |
| `evidence_hard_to_find` | couldn't find the cited law or article |
| `proof_confusing` | opened the proof or steps and was confused |
| `boxes_hard_to_find` | couldn't find the photo with the sign boxes |
| `followup_unclear` | re-attached the photo or opened a new chat for a follow-up |
| `followup_misread` | a follow-up was rewritten into the wrong question ("Hiểu câu hỏi là: …" doesn't match what they meant; write both in `notes`) |
| `history_hard_to_find` | couldn't find the history or the old chat |
| `feedback_hard_to_find` | couldn't find the right/wrong or correction buttons |
| `fallback_confusing` | confused by the RAG badge ("chưa được hệ luật kiểm chứng") |
| `fallback_off` | the RAG was down, so a question stayed undecided |
| `mobile_layout` | a layout problem on a phone |
| `error_message` | saw an error message (write which one in `notes`) |

## 5. Scoring

```bash
.venv/bin/python eval/uat/score_sus.py eval/runs/uat/responses.csv --observations eval/runs/uat/observations.csv --json eval/runs/uat/summary.json
```

It prints:
- the four targets, with pass or fail;
- SUS, CSAT and task success, each with its 95% CI;
- results by tester group and by device;
- where the free-question photos came from;
- the issue tags.

**Server-side numbers, aggregates only.** Run this on the server for each session day's window, then add the days together:

```bash
docker compose exec -T api python - --since 2026-11-26T01:00 --until 2026-11-26T11:00 < eval/uat/turn_stats.py
```

It reports answers on a **photo seen before** (the fixed photos, after the dry run) separately from the **first question on a new photo** (the real wait).

Then fill in `report_template.md` and save it as `docs/results/uat-<date>.md`.

## 6. Afterwards

- **Raw files stay local:** the form's CSV, the log, `photos_used.csv` and the notes go in `eval/runs/uat/`, which is gitignored. Delete them after the defense, along with the server's data (`docs/status.md`, open items).
- **Commit only** the aggregate report.
