from __future__ import annotations

# Hosted routes live in control_plane/app.py; this module is kept only so existing imports
# (pr-reviewer-api script entry point, tests importing pr_reviewer.web.app) keep working. It must
# never fork the webhook into a second implementation, so it re-exports the same FastAPI app rather
# than redefining it.
from pr_reviewer.control_plane.app import app, main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()
