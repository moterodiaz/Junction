"""Modal entry point: serves app.main on a public https/wss URL (PRD section 4).

Deploy from the repo root:  modal deploy backend/app/modal_app.py
Not imported by tests: `modal` is not in backend/requirements.txt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import modal

REMOTE_BACKEND = "/root/backend"

# Locally this file is backend/app/modal_app.py; in the container Modal runs it as
# /root/modal_app.py next to the uploaded /root/backend. Use whichever holds the app.
_HERE = Path(__file__).resolve().parent
BACKEND_DIR = next(path for path in (_HERE.parent, _HERE / "backend")
                   if (path / "app" / "config.py").is_file())

sys.path.insert(0, str(BACKEND_DIR))
from app.config import MODAL_SECRET_NAME  # noqa: E402

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(BACKEND_DIR / "requirements.txt"))
    .pip_install_from_requirements(str(BACKEND_DIR / "stt" / "requirements.txt"))  # faster-whisper
    # Never upload local secrets or build junk: keys come only from the Modal secret.
    .add_local_dir(BACKEND_DIR, REMOTE_BACKEND,
                   ignore=[".env", "**/.env", ".venv", "**/__pycache__", "tests"])
)

app = modal.App("metalab", image=image)


@app.function(
    secrets=[modal.Secret.from_name(MODAL_SECRET_NAME)],
    # Generated images live in this process's memory (backend/ai/image.py), so a second
    # container would 404 on images it did not make. One container serves 20 at once.
    max_containers=1,
    scaledown_window=300,  # stay warm for 5 min after a request; set min_containers=1 for the demo
    timeout=600,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    sys.path.insert(0, REMOTE_BACKEND)
    import stt
    from app.main import create_app

    fastapi_app = create_app(require_keys=True)  # a missing key in the secret fails the deploy here
    stt.warm()  # download and load Whisper now, so the first spoken request does not wait for it
    return fastapi_app
