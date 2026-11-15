# Phase 2 plan: question parser (as approved)

DESIGN.md roadmap phase 2. **Gate:** at least 90% program accuracy on reviewed public_dev intents, reported with a 95% confidence interval.

Before phase 2 started, two fixes were made, each in its own commit:
- `every_vehicle` treats members on both sides of a threshold as counterexamples;
- the catalog's review flag became `reviewed_by` (human | assistant | none), with a separate `visual_reviewed_by`.

## Changes the owner made at approval

1. **Unreadable-sign relevance.** A closed-world verdict becomes unknown only if the unreadable sign could bear on the claim, judged from its visible shape and colour category. A red-bordered circle could prohibit; a blue rectangular information sign cannot. Tests cover both cases. In the full pipeline, unknowns caused by unreadable signs go to the fallback. (Done: `6193e85`.)
2. **Effort comparison.** Parser effort is configurable. The eval includes runs of Haiku 5.5 at `low` and at the default effort on public_dev, reporting accuracy and cost for each.
3. **Confidence interval on the gate.** The gate score is reported with a 95% CI.

## Work items

1. **API setup** (`vqa/llm/`, done: `ab2baf3`).
   - `ANTHROPIC_API_KEY` comes from the environment and is never committed.
   - Every call's tokens and cost go to `logs/api_calls.jsonl` (gitignored).
   - The spend guard stops a run before a call whose worst case would exceed the limit (default $2; `--max-spend` / `VQA_SPEND_LIMIT`).
2. **Parser** (`vqa/parsing/`, done: `49169db`).
   - One Claude call with structured output turns a Vietnamese question into a `QueryProgram`. It covers the full DSL: forbidden, choose, is_sign, all_of/any_of, which_vehicles, lane_vehicles, speed_limit, every_vehicle.
   - Enums come from the ontology and the catalog. The DSL spec and few-shots go in a cached system prompt.
   - A validator checks each program; on failure the parser retries once with the error message.
   - **Changed by the owner on 2026-11-15:** no structured output. The parser asks for one JSON object in plain text: bare, or in a ```json fence. The typed wire models (`from_wire`), the validator and the dry run check it. Malformed JSON or a failed check gets exactly one retry with a short error, through the spend guard. A refusal or a reply cut off at `max_tokens` is an error, with no retry. The prompt is `prompts/parser/v3`: v2 plus a "reply with only the JSON object" line.
     - Reason: the API's documented limits for strict schemas are at most **24 optional parameters** and **16 parameters with union types** (`anyOf` or nullable), counted across all strict schemas in a request. The DSL has about 60 optional fields. Three gold-drafting requests were rejected with "The compiled grammar is too large", and none was billed. The two schema changes in between, `734135e` and `7ff868d`, did not get under the limit.
     - Enums are no longer enforced by the API. Vehicle classes, actions, sign codes and meanings are checked in Python instead.
   - The defaults from CLAUDE.md are applied and recorded in `defaults_applied`.
   - The default model is Haiku 5.5. Questions outside the DSL come back as `out_of_scope`.
3. **Few-shot sources.** Few-shot examples come from public_dev and train only, never public_holdout or private. This is enforced by a test.
4. **Gold intents** (`eval/gold_intents.py`, tooling done: `b7e648c`).
   - The script drafts programs for the 48 public_dev questions that are not few-shots, and 40 train questions, with Opus 5.5. It sends sequential calls with caching (`run`); the Batch API path is the fallback.
   - **Changed by the owner on 2026-11-15:** the train sample went from 150 random questions to 40, to save API budget. The owner has rewritten the train questions to read more naturally. The 40 are spread evenly over rough question categories, one per image where possible (`spread_sample`).
   - It writes `drafts.jsonl` and `review.csv` (question, draft program, owner verdict or correction).
   - The cost estimate is shown before running. The run is waiting for the owner's go-ahead.
   - **Changed by the owner on 2026-11-15:** drafting goes one call at a time with prompt caching (`run`), not through the Batch API, because a batch's caching is best effort. The run stops after call 2 if less than 90% of the prompt was read from the cache. The batch path (`submit` / `collect`) stays as the fallback.
   - No gold intents for public_holdout or private: those are scored end to end only.
5. **Eval script** (`eval/parser_eval.py`, done: `ecadd29`): program exact match, slot F1, and out-of-scope precision and recall on the reviewed gold. Also the gate score with a 95% CI, the effort comparison, and every accuracy on all images and on non-duplicate images.
   - **Gate definition, fixed on 2026-11-15 before any Haiku result:**
     - The gate set is the public_dev rows of `gold_intents_v1.jsonl`, minus the prompt's public_dev few-shots (public_natural_0026, 0097, 0082) and the rows the owner skipped. That leaves 47 rows, 8 of them out of scope.
     - Out-of-scope gold rows count. A prediction matches one only if it is out of scope too.
     - A parse failure after the retry, or a missing prediction, counts as wrong.
     - The gate passes if the point estimate of program accuracy is ≥ 90%. It is reported with a 95% Wilson CI.
     - Both sides are normalized before comparing:
       - Forbidden is compiled, inside all_of / any_of too;
       - `verify(expect=true)` is treated as the bare claim;
       - defaults are filled in, with context year 2025;
       - choice labels are ignored.
     - A prediction counts as correct if it equals the gold program or any `also_accept` program.

## Decisions (D1–D6, accepted)

- **D1, one-level nesting.** The wire models cap nesting at one level: claims inside verify / choose / all_of / any_of are plain claims.
  - The original reason, that structured outputs reject recursive schemas, no longer applies, because no schema is sent since `c1addf3`.
  - The owner kept the cap for now (2026-11-15). It still covers every question form seen in the audits. Lifting it would be a separate decision.
- **D2, question only.** In phase 2 the parser sees only the question; there is no perception yet, so there is no scene sign list. That input stays optional.
- **D3, few-shot selection.**
  - Gold drafting uses about 12 seed examples written from train. 16 were written.
  - The parser's final few-shots are picked from the reviewed gold, mostly train.
  - After the train rewrite, the seed examples moved to `prompts/parser/v2`: the same programs with the new question text. train_40 was dropped because its new wording no longer fits its program, which leaves 15.
  - v2 also has three public_dev few-shots in the "… đúng hay sai?" form, which the rewritten train no longer has: public_natural_0026, 0097 and 0082. As D3 requires, they are excluded from the gate score, and they are not drafted.
  - Any public_dev question used as a few-shot is excluded from the gate score.
- **D4, drafting effort.** Opus drafts at `medium` effort.
- **D5, alternative programs.** Gold may list alternative correct programs (`also_accept`), e.g. selecting a sign by code or by meaning.
- **D6, local log.** The API log stays local (`logs/`, gitignored).

## Implementation notes

- **Gold working files stay local.** `questions.jsonl`, `drafts.jsonl`, `review.csv` and `batch.json` contain dataset question text, so they are gitignored. `gold_intents_v1.jsonl` keeps ids and programs only.
- **Missing years in gold drafting.** They are filled with 2025, the year the dataset's questions come from. The parser itself uses the current year unless one is given.
- **Before comparing programs**, both gold and prediction are normalized: `Forbidden` compiled, `verify(claim, expect=true)` treated as the bare claim, defaults filled in, choice labels ignored.
