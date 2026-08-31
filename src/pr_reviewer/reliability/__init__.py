"""Shared retry, circuit, and budget policy. No hosted or runner store imports.

Retry and circuit are used on both planes. Budget policy lives here: unset means deny.
Hosted aggregate reservation executes in control_plane.budget; per-job reservation
executes in local_store.budget. This package must not import hosted or runner stores.
"""
