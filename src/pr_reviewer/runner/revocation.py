"""Immediate stop of new runner work after revocation (Runtime Task 9).

A revoked runner finishing its current job is arguable. A revoked runner claiming a new job
after that is not. This gate is checked before every claim, not at the next poll boundary: once
the control plane has said the runner or installation is revoked, process_once returns without
opening a new lease.
"""

from __future__ import annotations


class RevocationGate:
    def __init__(self) -> None:
        self._stop_new_work = False
        self._revoked_installations: set[int] = set()

    def allow_new_work(self) -> bool:
        return not self._stop_new_work

    def note_runner_revoked(self) -> None:
        self._stop_new_work = True

    def note_installation_revoked(self, installation_id: int) -> None:
        self._revoked_installations.add(installation_id)
        self._stop_new_work = True
