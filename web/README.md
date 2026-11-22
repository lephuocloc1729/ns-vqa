# Web UI

React + Vite + TypeScript, with no component library. The UI text is in Vietnamese, and it has light and dark modes. It is laid out like a chat app. On a wide screen there are three columns: the history sidebar, the conversation with the question box at the bottom, and the photo with its sign boxes. Below 1180 px the history moves into a drawer. On a phone the photo sits under the top bar and can be collapsed.

## Run

```bash
cd web && npm install
npm run dev          # http://localhost:5173; /v1, /health, /metrics, /version go to http://localhost:8000
```

The API runs on its own: `uvicorn --factory app.api.main:create_app --port 8000`, with the `VQA_*` settings in `docs/status.md`. To send the proxy somewhere else, set `VQA_API_URL=http://host:port npm run dev`.

To try the UI without Claude calls, start the real API with a fake pipeline (the same one the end-to-end test uses):

```bash
.venv/bin/python web/e2e/fake_api.py --port 8000
```

A question containing "RAG" goes down the RAG fallback path. Any other question is answered by the "rules", with a streamed draft that is withdrawn (`token_reset`) before the final text.

## Tests

```bash
npm run typecheck
npx vitest run         # SSE parser and per-turn reducer
npx playwright test    # starts web/e2e/fake_api.py and the Vite server itself; desktop + phone
```

The first Playwright run needs `npx playwright install chromium`. `PYTHON` picks the interpreter for the fake API (default `../.venv/bin/python`). CI runs both suites (`.github/workflows/ci.yml`, jobs `web` and `web-e2e`).

## How it works

- `src/lib/sse.ts`: `POST /v1/ask/stream` is read with `fetch` and a stream reader, because `EventSource` cannot upload. A small parser turns the body into events.
- `src/lib/turn.ts`: one turn's state, built from the events. Stage events (`started`, `perception`, `parsed`, `engine`, `route`) become the stage list, with their times. `token` events add to the streamed text and `token_reset` clears it. The `answer` event is authoritative and replaces the streamed text.
  - A stream that closes without `answer` or `error` counts as dropped. The client then fetches `GET /v1/turns/{id}` until the server has finished the turn.
- Sign boxes come from the `perception` event, in original-photo pixels, and are drawn in an SVG overlay that uses the photo's own coordinates. Confidence is shown by line style as well as colour: high is a solid line, medium dashed, low dotted.
- Below the answer:
  - notes for unknown answers, `reading_choice` and low-confidence signs;
  - for `basis` containing `rag`, the RAG badge and the retrieved laws with their text, kept apart from the rule citations;
  - the rule citations as chips;
  - the proof tree;
  - feedback buttons.
- History: the current session id, and the list of sessions seen in this browser, are kept in `localStorage` (wrapped in try/catch). Turns come from `GET /v1/sessions/{id}/turns`. A `#turn=<id>` link reopens one turn.
