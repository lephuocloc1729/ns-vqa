# SignCite UAT: moderator notes

These notes are for the person who runs the sessions. Testers get `task_sheet.md` and the form (`form_questions.md`). Results are scored by `score_sus.py` and `turn_stats.py`, then written up in `report_template.md`.

**Target (plan 3.3, reduced in the 9-day schedule):**
- 15–20 testers; 10–12 is the floor.
- Mix: drivers, students, and **2–3 people who know traffic law**.
- Each tester does 5 fixed tasks, asks 5 questions of their own, then fills in the form. That takes about 30 minutes in all.

## 1. Before the first session (once)

**The five photos** (`Ảnh 1`–`Ảnh 5`):
- **The owner takes them on the street.** Never use dataset photos: testers would see train or test images, and the pipeline has seen most train scenes.
- **What each one needs to show:**

  | Photo | Used in | Needs |
  |---|---|---|
  | Ảnh 1 | T1, T5 | One clear sign, any kind |
  | Ảnh 2 | T2, T3 | A prohibitory sign that treats cars and motorbikes differently. For example: P.103a "cấm ô tô" (car: no, motorbike: yes), or a P.104/P.106 family sign. |
  | Ảnh 3 | T4 | A speed limit sign (P.127, a number in a red circle) |
  | Ảnh 4, Ảnh 5 | free questions | Several signs, or a sign with an auxiliary plate (times, vehicle types) |

- **Rules for the photos:** daylight; the sign at least about 80 px tall; no readable faces or number plates; JPEG or PNG under 10 MB.

**Dry run** (owner's go-ahead on cost first, about $0.10):
- Ask each fixed task's question once on signcite.xyz and write down the expected answer, the sign code and the cited article in the table below.
- **If an answer is wrong or undecided, change the photo**, not the task. The fixed tasks test the interface, not the model.
- The dry run fills the scene cache for these photos. Testers will therefore get faster answers on T1–T4 than on their own photos. The report states this (section 6).

| Task | Question | Expected answer | Sign | Article |
|---|---|---|---|---|
| T1 | Biển báo này có nghĩa là gì? | | | |
| T2 | Xe ô tô con có được đi vào đường này không? | | | |
| T3 | Xe máy có được đi vào không? | | | |
| T4 | Tốc độ tối đa cho phép ở đây là bao nhiêu? | | | |

**Other preparation:**
- **Participant IDs:** `P01`, `P02`, … in the order people come. Write each ID on that person's task sheet; the form asks for it.
- **The form:** build it from `form_questions.md` and test it once with a dummy answer.
  - Then download the CSV and run `score_sus.py` on it.
  - Delete the dummy row before the real sessions.
- **The spend cap** (owner's decision): about 20 testers × ~12 questions × $0.015 ≈ $3.6, plus retries.
  - Set `VQA_SPEND_LIMIT` in the server's `.env`.
  - Restart the API before each session day, because the cap counts from a restart.

## 2. Each session day (the server)

**Before the first tester:**
1. Rent the GPU and run `bash docker/rag-session.sh on <host> <port>` on the server (`docs/runbooks/gpu-session.md`).
2. Check `/version`: the fallback is `rag`, there are 10 answer slots, and the RAG cache is on.
3. Write down the start time in UTC. `turn_stats.py` uses it.
4. Ask one question yourself to warm everything up.

**After the last tester:**
1. `bash docker/rag-session.sh off`, then destroy the GPU.
2. Write down the end time.

**If the RAG or GPU is down mid-session:**
- Answers the rules can't decide show "Hệ luật chưa quyết định được…". Testing continues.
- Tag the attempt `fallback_off` and note the time.

## 3. Running a session

**Formats:**
- **In person or on a video call with screen sharing (preferred):** you fill in the observation log.
- **Unmoderated:** the tester gets the sheet and the form only. The form's `[OK1]`–`[OK5]` answers stand in for the log, and the report must call those rates **self-reported**.

**Script (say it in your own words):**
1. *"Cảm ơn bạn. Hôm nay mình thử phần mềm, không thử bạn. Không có câu trả lời sai."*
2. *"Bạn vừa làm vừa nói to suy nghĩ nhé: đang tìm gì, mong đợi gì, thấy lạ chỗ nào."*
3. *"Mình sẽ không giúp trong lúc làm, vì mình muốn biết phần mềm tự nó có rõ không. Bí quá 3 phút thì mình chuyển nhiệm vụ."*
4. Give them the password for the site, never in a group chat. Then give them Ảnh 1–5.

**While they work:**
- **Don't help.** If asked, answer *"Bạn nghĩ nên làm gì?"*.
- After 3 minutes on one task, mark it `fail` and move on.
- **Time each task:** from the moment the tester starts reading it to the moment they state the result. The answer's waiting time is included.
- **Outcomes:**
  - `success`: the task sheet's ✅ condition is met without help.
  - `partial`: half of the condition is met (e.g. T2's verdict but not the article; T4 typed instead of spoken), or it is met after one hint.
  - `fail`: otherwise, or the tester gave up.
- The answer being *legally wrong* is not a task failure. Tag it `answer_wrong` and write what was asked.

**Afterwards (2 minutes):**
- *"Điều gì làm bạn khó chịu nhất?"*
- *"Bạn có tin câu trả lời không? Vì sao?"*
- Write the answers in `notes`, then send the form link.

## 4. The observation log

- **Where:** copy `observation_log_template.csv` to `eval/runs/uat/observations.csv`. That folder is gitignored, so the log never gets committed.
- **Rows:** one row per participant and task.
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
| `history_hard_to_find` | couldn't find Lịch sử or the old chat |
| `feedback_hard_to_find` | couldn't find đúng/sai or Sửa đáp án |
| `fallback_confusing` | confused by the RAG badge ("chưa được hệ luật kiểm chứng") |
| `fallback_off` | the RAG was down, so a question stayed undecided |
| `mobile_layout` | a layout problem on a phone |
| `error_message` | saw an error message (write which one in `notes`) |

## 5. Scoring

```bash
.venv/bin/python eval/uat/score_sus.py eval/runs/uat/responses.csv --observations eval/runs/uat/observations.csv --json eval/runs/uat/summary.json
```

**Server-side numbers, aggregates only.** Run this on the server for each session day's window, then add up the days:

```bash
docker compose exec -T api python - --since 2026-11-26T01:00 --until 2026-11-26T11:00 < eval/uat/turn_stats.py
```

Then fill in `report_template.md` and save it as `docs/results/uat-<date>.md`.

## 6. Afterwards

- **Raw files stay local:** the form's CSV, the log and the notes go in `eval/runs/uat/`, which is gitignored. Delete them after the defense, along with the server's data (`docs/status.md`, open items).
- **Commit only** the aggregate report.
