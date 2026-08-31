"""Runner-side notification policy, preview, and fan-out.

Send is injected by the caller. This package must not import connectors/ or db:
connectors/github.py imports pr_reviewer.db.client, so a direct import would fail
the transitive runner-side guard.
"""
