# Backend

FastAPI orchestrator for MetaLab (PRD section 4). Tests: `backend/test.sh`.

## Run locally

```sh
cd backend && .venv/bin/uvicorn app.main:app --reload   # after backend/test.sh has built .venv
```

## Deploy on Modal

One-time setup:

1. `uv tool install modal`, then `modal setup` (browser login).
2. Create the secret the app reads (names in `backend/.env.example`):
   ```sh
   modal secret create metalab NVIDIA_API_KEY=... NVIDIA_BASE_URL=... MODEL_READ=... GEMINI_API_KEY=...
   ```

Deploy from the repo root:

```sh
modal deploy backend/app/modal_app.py
```

It prints a URL like `https://<workspace>--metalab-web.modal.run`. Then:

- Phone app: `wss://<workspace>--metalab-web.modal.run/ws`
- Health check: `curl https://<workspace>--metalab-web.modal.run/health` returns `{"ok":true}`
- Add `IMAGE_BASE_URL=https://<workspace>--metalab-web.modal.run` to the `metalab` secret (generated images are served from it), then deploy again.

`backend/.env` is never uploaded; keys come only from the Modal secret. For the demo, set `min_containers=1` in `modal_app.py` so the first request does not wait for a cold start (this keeps one container running and billed).
