from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from pr_reviewer.config import get_settings
from pr_reviewer.control_plane.approval_api import router as approval_router
from pr_reviewer.control_plane.oauth_api import router as oauth_router
from pr_reviewer.control_plane.pairing_api import router as pairing_router
from pr_reviewer.control_plane.runner_jobs import router as runner_jobs_router
from pr_reviewer.github import verify_github_signature
from pr_reviewer.jobs import enqueue_review_job

MAX_WEBHOOK_BODY_BYTES = 1024 * 1024

app = FastAPI(title="PR Reviewer")
app.include_router(pairing_router)
app.include_router(oauth_router)
app.include_router(approval_router)
app.include_router(runner_jobs_router)


@app.post("/api/github/webhook")
async def github_webhook(request: Request) -> JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            return JSONResponse({"error": "invalid content length"}, status_code=400)
        if declared_size > MAX_WEBHOOK_BODY_BYTES:
            return JSONResponse({"error": "payload too large"}, status_code=413)

    body = await request.body()
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        return JSONResponse({"error": "payload too large"}, status_code=413)

    signature = request.headers.get("x-hub-signature-256", "")
    delivery_id = request.headers.get("x-github-delivery", "")
    event_name = request.headers.get("x-github-event", "")

    if not delivery_id or not event_name:
        return JSONResponse({"error": "missing github headers"}, status_code=400)

    if not verify_github_signature(body, signature, get_settings().github_webhook_secret):
        return JSONResponse({"error": "invalid signature"}, status_code=401)

    try:
        payload: Any = await request.json()
    except ValueError:
        return JSONResponse({"error": "malformed json"}, status_code=400)

    result = enqueue_review_job(delivery_id, event_name, payload)
    return JSONResponse({"result": result}, status_code=202 if result == "enqueued" else 200)


def main() -> None:
    uvicorn.run("pr_reviewer.control_plane.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
