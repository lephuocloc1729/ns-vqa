# Hand-written fixtures for train questions

Each `train_*.json` describes one question from the train split. The scene graph is hand-written from the image, so these tests check the engine alone, with perception and parsing left out.

Fields:

- `question_id`, `image_id`: the dataset ids. Question text and gold answers stay in the dataset and are not copied here.
- `summary`: our own one-line paraphrase of the question.
- `scene`: a `SceneGraph`.
- `cases`: one entry per program. Each has:
  - `program`: a `Program`, i.e. one of the intents.
  - `expect.verdict`: the engine verdict.
  - `expect.value` (optional): a subset that must match `Answer.value`. Dicts match on their listed keys; lists must have the same length and match element by element.
- `core_articles`: the article ids from the question's `relevant_articles` that the cited set must contain, taken together over all cases.
- `not_core`: article ids from `relevant_articles` left out of `core_articles`, each with the reason.
- `notes` (optional): workarounds in the scene or program, so known gaps stay visible.
- `citation_xfail` (optional): the reason the citation check is expected to fail, used for known engine gaps.

The citation test is marked `xfail` only when `citation_xfail` is set. It is strict, so it starts failing once the gap is fixed, and then the marker should be removed.
